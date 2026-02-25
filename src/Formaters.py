import os.path
import time
from datetime import datetime
from typing import Callable
from github.Branch import Branch
from github.Repository import Repository
from github.Issue import Issue
from github.NamedUser import NamedUser
from github.PullRequest import PullRequest
from github.Commit import Commit
from github.Comparison import Comparison
import pathlib
from github import GithubException
from git import Repo as LGitRepo
from git import Commit as LGitCommit
from git.exc import GitError
from github.GithubException import RateLimitExceededException, UnknownObjectException
from Rate_Limiter import wait_for_reset_ratelimit
import tempfile
from Logger import log
from collections import defaultdict


def get_organization(organization_name: str, github, scraper_nr):
    try:
        return github.get_organization(organization_name)
    except UnknownObjectException:
        try:
            return github.get_user(organization_name)
        except Exception as e:
            log(scraper_nr, "ERROR", f"Failed to get user {e}")
            raise Exception("Failed to get user")


def get_formatted_issues(repository: Repository, github_gmail, scraper_nr):
    issues = []
    issue_list = list(repository.get_issues(state="all"))

    for issue in issue_list:
        formatted_issue = None
        try:
            formatted_issue = __retry_request(
                __format_issue, github_gmail, scraper_nr, repository.name, issue
            )
        except Exception as e:
            log(scraper_nr, "WARNING", f"Failed to get issue {e}. Skipping it")
        if formatted_issue:
            issues.append(formatted_issue)

    return issues


def get_formatted_branches(repository: Repository, github_gmail, scraper_nr):
    branches = []
    for branch in repository.get_branches():
        formatted_branch = None
        try:
            formatted_branch = __retry_request(
                __format_branch, github_gmail, scraper_nr, repository, branch
            )
        except Exception as e:
            log(scraper_nr, "WARNING", f"Failed to get branch {e}. Skipping it")
        if formatted_branch:
            branches.append(formatted_branch)
    return branches


def get_formatted_contributions(
    repository: Repository, organization_name: str, github_gmail, scraper_nr
):
    contributions = []

    try:
        stats_contributors = repository.get_stats_contributors()
        if stats_contributors:
            for contributor in stats_contributors:
                formatted_contributor = None
                try:
                    formatted_contributor = __retry_request(
                        __format_contributors,
                        github_gmail,
                        scraper_nr,
                        organization_name,
                        repository,
                        contributor,
                        "",
                    )
                except Exception as e:
                    log(
                        scraper_nr,
                        "WARNING",
                        f"Failed to get contributor {e}. Skipping it",
                    )

                if formatted_contributor:
                    contributions.append(formatted_contributor)
        else:
            log(scraper_nr, "WARNING", "Failed to fetch stats contributors")
    except GithubException as ge:
        if ge.status in {500, 502}:
            contributions.append(
                __format_contributors(
                    organization_name, repository, None, str(ge.status)
                )
            )
    except Exception as e:
        contributions.append(
            __format_contributors(organization_name, repository, None, str(e))
        )

    return contributions


def get_formatted_users(repository: Repository, github_gmail, scraper_nr):
    users = []

    try:
        for user in repository.get_contributors():
            formatted_user = None
            try:
                formatted_user = __retry_request(
                    __format_user, github_gmail, scraper_nr, repository, user
                )
            except Exception as e:
                log(scraper_nr, "WARNING", f"Failed to get user {e}. Skipping it")
            if formatted_user:
                users.append(formatted_user)
    except Exception as e:
        log(scraper_nr, "WARNING", "Failed to fetch users!" + str(e))
    return users


def get_formatted_forks(
    repository: Repository, organization_name: str, github_gmail, scraper_nr
):
    forks = []
    for fork in repository.get_forks():
        retries = 3
        while retries > 0:
            try:
                try:
                    fork_owner = fork.owner.name
                except (AttributeError, UnknownObjectException):
                    fork_owner = "None"
                try:
                    fork_owner_login = fork.owner.login
                except (AttributeError, UnknownObjectException):
                    fork_owner_login = "None"
                try:
                    fork_owner_id = fork.owner.id
                except (AttributeError, UnknownObjectException):
                    fork_owner_id = "None"

                # Compare the branches (default is usually 'main' or 'master')
                try:
                    comparison: Comparison = fork.compare(
                        f"{organization_name}:{repository.default_branch}",
                        fork.default_branch,
                    )
                except Exception:
                    comparison = None

                try:
                    commits_ahead = comparison.ahead_by
                except Exception:
                    commits_ahead = "Error."

                try:
                    commits_behind = comparison.behind_by
                except Exception:
                    commits_behind = "Error."

                try:
                    fork_subs = fork.subscribers_count
                except Exception as e:
                    fork_subs = "Error."

                forks.append(
                    __format_fork(
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
                )
                break
            except RateLimitExceededException:
                wait_for_reset_ratelimit(scraper_nr, github_gmail)
            retries -= 1
        if retries == 0:
            log(scraper_nr, "ERROR", "Failed to format fork 3 times")
    return forks


def get_formatted_pulls(
    repository: Repository, organization_name: str, github_gmail, scraper_nr
):
    pulls = []
    for pull in repository.get_pulls(state="all"):
        formatted_pull = None
        try:
            formatted_pull = __retry_request(
                __format_pull,
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


def get_formatted_commits(repository: Repository, organization_name: str, scraper_nr: int):
    formatted_commits = []
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        repo_clone = None
        tmp_dir = pathlib.Path(os.path.join(tmp_dir_name, str(scraper_nr)))
        try:
            LGitRepo.clone_from(repository.clone_url, f"{tmp_dir}")
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
                formatted_commits.append(
                    __format_commit(organization_name, repository, commit)
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
    readme = __get_readme(repository)
    created_at = __check_none(repository.created_at)
    updated_at = __check_none(repository.updated_at)
    pushed_at = __check_none(repository.pushed_at)
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


def __retry_request(func: Callable, github_gmail: Github, scraper_nr, *args, **kwargs):
    retries = 5
    while retries > 0:
        try:
            if github_gmail.get_rate_limit().rate.remaining < 100:
                wait_for_reset_ratelimit(scraper_nr, github_gmail)
            return func(*args, **kwargs)
        except RateLimitExceededException:
            wait_for_reset_ratelimit(scraper_nr, github_gmail)
            retries -= 1
        except GithubException as e:
            if e.status == 403:
                log(scraper_nr, "ERROR", f"Access denied for {func.__name__}")
                return None
            raise
    log(scraper_nr, "ERROR", f"Failed {func.__name__} {5} times")
    return None


def __format_timestamp(timestamp):
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def __check_none(value):
    if value:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return "None"


def __get_readme(repository: Repository):
    try:
        return repository.get_readme().decoded_content.decode("utf-8")
    except:
        return ""


def __format_issue(repo_name: str, issue: Issue) -> list:
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
        __check_none(issue.created_at),
        __check_none(issue.closed_at),
        getattr(user, "email", None),
        getattr(user, "login", None),
        getattr(user, "name", None),
        getattr(user, "id", None),
        comments,
    ]


def __format_branch(repo: Repository, branch: Branch) -> list:
    return [repo.name, branch.name, branch.protected, branch.last_modified]


def __format_contributors(
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


def __format_user(repo: Repository, user: NamedUser) -> list:
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
        __check_none(user.created_at),
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
        __check_none(user.updated_at),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]


def __format_fork(
    organization_name: str,
    repo: Repository,
    fork: Repository,
    fork_owner: NamedUser,
    fork_owner_id: NamedUser,
    fork_owner_login: NamedUser,
    fork_subs: Repository,
    commits_ahead: int,
    commits_behind: int,
) -> list:
    return [
        organization_name,
        repo.name,
        fork.name,
        fork_owner_login,
        __check_none(fork.created_at),
        __check_none(fork.pushed_at),
        __check_none(fork.updated_at),
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


def __format_pull(organization_name: str, repo: Repository, pull: PullRequest) -> list:
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
        __check_none(pull.created_at),
        __check_none(pull.updated_at),
        __check_none(pull.closed_at),
        __check_none(pull.merged_at),
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


def __format_commit(organization_name: str, repo: Repository, commit: LGitCommit) -> list:
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
        __format_timestamp(commit.committed_datetime),
        __format_timestamp(commit.authored_datetime),
        commit.stats.total["files"],
        commit.binsha.hex(),
    ]
