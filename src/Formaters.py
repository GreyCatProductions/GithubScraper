import os.path
import time
from datetime import datetime
from typing import Callable
from github import Github
from github.Branch import Branch
from github.Repository import Repository
from github.Issue import Issue
from github.NamedUser import NamedUser
from github.PullRequest import PullRequest
from github.Commit import Commit
from github.Comparison import Comparison
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
import pathlib
from github import GithubException
from git import Repo as LGitRepo
from git import Commit as LGitCommit
from git.exc import GitError
from github.GithubException import RateLimitExceededException, UnknownObjectException
import tempfile
from Logger import log
from collections import defaultdict

from RetryWrapper import retry_request


def get_organization(organization_name: str, github: Github, scraper_nr):
    try:
        return retry_request(
            github.get_organization, github, scraper_nr, organization_name
        )
    except UnknownObjectException:
        try:
            return retry_request(github.get_user, github, scraper_nr, organization_name)
        except UnknownObjectException:
            log(scraper_nr, "ERROR", f"Neither org nor user found: {organization_name}")
            return None
        except Exception as e:
            log(scraper_nr, "ERROR", f"Failed to get user {organization_name}: {e}")
            return None


def get_formatted_issues(repository: Repository, github_gmail, scraper_nr):
    issues = []
    issue_iter = retry_request(
        repository.get_issues, github_gmail, scraper_nr, state="all"
    )
    if not issue_iter:
        log(scraper_nr, "ERROR", f"Could not fetch issues for {repository.full_name}")
        return issues

    for issue in issue_iter:
        try:
            formatted_issue = retry_request(
                _format_issue, github_gmail, scraper_nr, repository.name, issue
            )
            if formatted_issue:
                issues.append(formatted_issue)
        except Exception as e:
            log(
                scraper_nr,
                "WARNING",
                f"Failed to format issue {getattr(issue, 'number', '?')}: {e}. Skipping it",
            )

    return issues


def get_formatted_branches(repository: Repository, github_gmail: Github, scraper_nr):
    branches: list = []

    branch_iter = retry_request(repository.get_branches, github_gmail, scraper_nr)
    if not branch_iter:
        log(scraper_nr, "ERROR", f"Could not fetch branches for {repository.full_name}")
        return branches

    for branch in branch_iter:
        try:
            formatted = retry_request(
                _format_branch, github_gmail, scraper_nr, repository, branch
            )
            if formatted:
                branches.append(formatted)
        except Exception as e:
            log(
                scraper_nr,
                "WARNING",
                f"Failed to format branch {getattr(branch, 'name', '?')} "
                f"for {repository.full_name}: {e}. Skipping it",
            )

    return branches


def get_formatted_contributions(
    repository: Repository, organization_name: str, github_gmail, scraper_nr
):
    def fallback(error: str):
        formatted = retry_request(
            _format_contributors,
            github_gmail,
            scraper_nr,
            organization_name,
            repository,
            None,
            error,
        )
        if not formatted:
            log(scraper_nr, "WARNING", "Failed to fetch stats contributors")
            return []
        return [formatted]

    try:
        stats_contributors = retry_request(
            repository.get_stats_contributors, github_gmail, scraper_nr
        )
    except GithubException as ge:
        if ge.status in {500, 502}:
            return fallback(str(ge.status))
        raise
    except Exception as e:
        return fallback(str(e))

    if not stats_contributors:
        log(scraper_nr, "WARNING", "Failed to fetch stats contributors")
        return []

    contributions = []
    for contributor in stats_contributors:
        try:
            formatted = retry_request(
                _format_contributors,
                github_gmail,
                scraper_nr,
                organization_name,
                repository,
                contributor,
                "",
            )
        except Exception as e:
            log(scraper_nr, "WARNING", f"Failed to get contributor {e}. Skipping it")
            continue

        if formatted:
            contributions.append(formatted)

    return contributions


def get_formatted_users(repository: Repository, github_gmail, scraper_nr):
    users = []

    try:
        users_fetch = retry_request(repository.get_contributors, github_gmail, scraper_nr)
        if not users_fetch:
            log(scraper_nr, "WARNING", "Failed to fetch users!" + str(e))
            return []
        
        for user in users_fetch:
            try:
                formatted_user = retry_request(
                    _format_user, github_gmail, scraper_nr, repository, user
                )
                if formatted_user:
                    users.append(formatted_user)
            except Exception as e:
                log(scraper_nr, "WARNING", f"Failed to get user {e}. Skipping it")
    except Exception as e:
        log(scraper_nr, "ERROR", "Unexpected error while trying to fetch users!" + str(e))
    return users


def get_formatted_forks(
    repository: Repository, organization_name: str, github_gmail, scraper_nr
):
    def safe_try_fork(fork: Repository):
        try:
            fork_owner: NamedUser | None = fork.owner
        except Exception:
            fork_owner = None

        if fork_owner:
            fork_owner_id: int | None = fork_owner.id
            fork_owner_login: str | None = fork_owner.login
        else:
            fork_owner_id = None
            fork_owner_login = None

        try:
            comparison: Comparison | None = fork.compare(
                f"{organization_name}:{repository.default_branch}",
                fork.default_branch,
            )
        except Exception:
            comparison = None

        commits_ahead = "No Comparison"
        commits_behind = "No Comparison"
        if comparison:
            commits_ahead = comparison.ahead_by
            commits_behind = comparison.behind_by

        try:
            fork_subs: int | None = fork.subscribers_count
        except Exception as e:
            fork_subs = None

        formated = _format_fork(
                organization_name,
                repository,
                fork,
                fork_owner,
                fork_owner_id,
                fork_owner_login,
                fork_subs,
                commits_ahead,
                commits_behind,
            )
        return formated
        
    forks = []
    forks_iter = retry_request(repository.get_forks, github_gmail, scraper_nr)
    if not forks_iter:
        log(scraper_nr, "ERROR", "Failed to get forks")
        return []
        
    for fork in forks_iter:
        formated_fork = retry_request(safe_try_fork, github_gmail, scraper_nr, fork)
        if not formated_fork:
            log(scraper_nr, "ERROR", f"Failed to get fork {fork.name}. Skipping it")
            continue
        forks.append(fork)
    return forks


def get_formatted_pulls(
    repository: Repository, organization_name: str, github_gmail, scraper_nr
):
    pulls = []
    pulls_iter = retry_request(repository.get_pulls, github_gmail, scraper_nr, state="all")
    if not pulls_iter:
        log(scraper_nr, "WARNING", f"Failed to get pulls for {repository.name}. Skipping it")
        return []
    
    for pull in pulls_iter:
        formatted_pull = None
        try:
            formatted_pull = retry_request(
                _format_pull,
                github_gmail,
                scraper_nr,
                organization_name,
                repository,
                pull,
            )
        except Exception as e:
            log(scraper_nr, "WARNING", f"Failed to get pull {e}. Skipping it")

        pulls.append(formatted_pull)
    return pulls


def get_formatted_commits(
    repository: Repository, organization_name: str, scraper_nr: int
):
    formatted_commits = []
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        repo_clone = None
        tmp_dir = pathlib.Path(os.path.join(tmp_dir_name, str(scraper_nr)))
        try:
            LGitRepo.clone_from(repository.clone_url, f"{tmp_dir}")
            return []
        except GitError:
            log(scraper_nr, "WARNING", f"Likely already exists repo: {repository.name}")
        except Exception as e:
            log(
                scraper_nr,
                "ERROR",
                f"An exception occurred for Repo: {repository.name} {e}",
            )

        try:
            repo_clone = LGitRepo(tmp_dir)
            for commit in repo_clone.iter_commits():
                try:
                    formatted_commits.append(
                        _format_commit(organization_name, repository, commit)
                    )
                except Exception as e:
                    log(
                        scraper_nr,
                        "WARNING",
                        f"Failed to process commit ({commit.binsha.hex()}) for {organization_name}",
                    )
        except Exception as e:
            log(
                scraper_nr,
                "ERROR",
                f"Failed to process commits for {repository.name}: {e}",
            )
        finally:
            if repo_clone is not None:
                repo_clone.close()
            time.sleep(1)
    return formatted_commits


def get_formatted_repository_data(
    repository: Repository, organization_name: str, scraper_nr: int
) -> tuple:
    try:
        readme = _get_readme(repository)
        created_at = _check_none(repository.created_at)
        updated_at = _check_none(repository.updated_at)
        pushed_at = _check_none(repository.pushed_at)
    except:
        log(scraper_nr, "ERROR", f"Failed to get metadata for {repository.name}!")
        readme = "Error"
        created_at = "Error"
        updated_at = "Error"
        pushed_at = "Error"
    try:
        license_val = repository.get_license()
        license_val = license_val.license.key
    except UnknownObjectException:
        license_val = "None"
    cur_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        languages = repository.get_languages()
    except Exception as e:
        log(scraper_nr, "WARNING", "Failed to get languages" + str(e))
        languages = ""

    repo_data = []
    summary_data = []

    try:
        repo_data = [
            organization_name,
            repository.name,
            repository.id,
            repository.forks_count,
            repository.stargazers_count,
            repository.watchers_count,
            repository.size,
            repository.open_issues_count,
            repository.subscribers_count,
            repository.network_count,
            repository.language,
            repository.description,
            pushed_at,
            created_at,
            updated_at,
            cur_time,
            repository.default_branch,
            readme,
            repository.fork,
            languages,
            license_val,
            repository.archived,
        ]

        summary_data = [
            organization_name,
            repository.name,
            repository.name,
            created_at,
            repository.size,
            repository.stargazers_url,
            repository.stargazers_count,
            repository.subscribers_url,
            repository.subscribers_count,
            repository.forks_count,
            repository.forks_count,
            repository.forks_url,
            repository.language,
            repository.description,
            created_at,
            updated_at,
            cur_time,
            repository.fork,
            languages,
            license_val,
            repository.archived,
        ]
    except Exception as e:
        log(scraper_nr, "WARNING", "Failed to get repository data" + str(e))
    return repo_data, summary_data


def _format_timestamp(timestamp):
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _check_none(value):
    if value:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return "None"


def _get_readme(repository: Repository):
    try:
        return repository.get_readme().decoded_content.decode("utf-8")
    except:
        return ""


def _format_issue(repo_name: str, issue: Issue) -> list:
    user = None

    try:
        user = issue.user
        comments = issue.comments
    except Exception as e:
        comments = 0

    return [
        repo_name,
        issue.title,
        issue.state,
        _check_none(issue.created_at),
        _check_none(issue.closed_at),
        getattr(user, "email", None),
        getattr(user, "login", None),
        getattr(user, "name", None),
        getattr(user, "id", None),
        comments,
    ]


def _format_branch(repo: Repository, branch: Branch) -> list:
    return [repo.name, branch.name, branch.protected, branch.last_modified]


def _format_contributors(
    organization_name: str, repository: Repository, contributor, error_message
):
    if error_message != "":
        return [
            organization_name,
            repository.name,
            "ERROR",
            error_message,
            datetime.now(),
        ]

    return [
        organization_name,
        repository.name,
        contributor.author.login,
        contributor.total,
        datetime.now(),
        contributor.author.id,
    ]


def _format_user(repo: Repository, user: NamedUser) -> list:
    return [
        repo.name,
        repo.id,
        user.login,
        user.name,
        user.id,
        user.bio,
        user.blog,
        user.company,
        user.collaborators,
        _check_none(user.created_at),
        user.disk_usage,
        user.email,
        user.events_url,
        user.followers,
        user.followers_url,
        user.following,
        user.following_url,
        user.hireable,
        user.location,
        user.plan,
        user.public_repos,
        user.type,
        _check_none(user.updated_at),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]


def _format_fork(
    organization_name: str,
    repo: Repository,
    fork: Repository,
    fork_owner: NamedUser | None,
    fork_owner_id: int | None,
    fork_owner_login: str | None,
    fork_subs: int | None,
    commits_ahead: int | str,
    commits_behind: int | str,
) -> list:
    return [
        organization_name,
        repo.name,
        fork.name,
        fork_owner_login,
        _check_none(fork.created_at),
        _check_none(fork.pushed_at),
        _check_none(fork.updated_at),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fork_owner,
        fork_owner_id,
        fork.has_downloads,
        fork.last_modified_datetime,
        fork.watchers_count,
        fork_subs,
        fork.open_issues_count,
        commits_ahead,
        commits_behind,
    ]


def _format_pull(organization_name: str, repo: Repository, pull: PullRequest) -> list:
    commit_to_prs = defaultdict(list)
    for commit in pull.get_commits():
        try:
            pull_head = pull.head.repo.full_name
        except:
            pull_head = ""
        commit_to_prs[commit.sha].append(
            {
                "pr_number": pull.number,
                "merged": pull.merged,
                "from_fork": pull_head != pull.base.repo.full_name,
            }
        )
    return [
        organization_name,
        repo.name,
        pull.id,
        pull.additions,
        pull.deletions,
        pull.changed_files,
        pull.comments,
        pull.state,
        pull.merged,
        _check_none(pull.created_at),
        _check_none(pull.updated_at),
        _check_none(pull.closed_at),
        _check_none(pull.merged_at),
        pull.user.name,
        pull.user.login,
        pull.user.id,
        pull.last_modified,
        pull.assignee,
        pull.assignees,
        pull.comments,
        pull.title,
        pull.merge_commit_sha,
        commit_to_prs,
    ]


def _format_commit(
    organization_name: str, repo: Repository, commit: LGitCommit
) -> list:
    author_login = getattr(commit.author, "login", None)
    committer_login = getattr(commit.committer, "login", None)
    return [
        organization_name,
        repo.name,
        repo.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        commit.message,
        commit.author.name,
        commit.author.email,
        author_login,
        commit.committer.name,
        commit.committer.email,
        committer_login,
        commit.stats.total["deletions"],
        commit.stats.total["insertions"],
        _format_timestamp(commit.committed_datetime),
        _format_timestamp(commit.authored_datetime),
        commit.stats.total["files"],
        commit.binsha.hex(),
    ]
