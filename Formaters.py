import time
from datetime import datetime
from typing import Callable
from github import Repository, Issue, NamedUser, PullRequest, Commit, Github
from github.Branch import Branch
import pathlib
from github import GithubException
from git import Repo
from git.exc import GitError
from github.GithubException import RateLimitExceededException, UnknownObjectException
from Rate_Limiter import wait_for_reset_ratelimit
import tempfile
from Logger import log

def get_organization(organization_name: str, github_gmail):
    try:
        return github_gmail.get_organization(organization_name)
    except UnknownObjectException:
        try:
            return github_gmail.get_user(organization_name)
        except Exception as e:
            log("ERROR", f"Failed to get user {e}")
            Exception("Failed to get organization")

def get_formatted_issues(repository: Repository, github_gmail):
    issues = []
    issue_list = list(repository.get_issues(state="all"))

    for issue in issue_list:
        formatted_issue = __retry_request(__format_issue, github_gmail, repository.name, issue)
        if formatted_issue:
            issues.append(formatted_issue)

    return issues

def get_formatted_branches(repository: Repository, github_gmail):
    branches = []
    for branch in repository.get_branches():
        formatted_branch = __retry_request(__format_branch, github_gmail,  repository, branch)
        if formatted_branch:
            branches.append(formatted_branch)
    return branches

def get_formatted_contributions(repository: Repository, organization_name: str, github_gmail):
    contributions = []

    try:
        stats_contributors = repository.get_stats_contributors()
        if stats_contributors:
            for contributor in stats_contributors:
                formatted_contributor = __retry_request(__format_contributors, github_gmail, organization_name,
                                                        repository, contributor, "")
                if formatted_contributor:
                    contributions.append(formatted_contributor)
        else:
            log("WARNING", "Failed to fetch stats contributors")
    except GithubException as ge:
        if ge.status in {500, 502}:
            contributions.append(__format_contributors(organization_name, repository, None, str(ge.status)))
    except Exception as e:
        contributions.append(__format_contributors(organization_name, repository, None, str(e)))

    return contributions

def get_formatted_users(repository: Repository, github_gmail):
    users = []
    for user in repository.get_contributors():
        formatted_user = __retry_request(__format_user, github_gmail, repository, user)
        if formatted_user:
            users.append(formatted_user)
    return users

def get_formatted_forks(repository: Repository, organization_name: str, github_gmail):
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
                    comparison = fork.compare(fork.default_branch,
                                              f"{organization_name}:{repository.default_branch}")
                    commits_ahead = comparison.ahead_by
                except Exception as e:
                    commits_ahead = "Error."

                try:
                    fork_subs = fork.subscribers_count
                except Exception as e:
                    fork_subs = "Error."

                forks.append(__format_fork(organization_name, repository, fork, fork_owner,
                                         fork_owner_id, fork_owner_login, fork_subs, commits_ahead))
                break
            except RateLimitExceededException:
                wait_for_reset_ratelimit(github_gmail)
            retries -= 1
        if retries == 0:
            log("ERROR", "Failed to format fork 3 times")
    return forks

def get_formatted_pulls(repository: Repository, organization_name: str, github_gmail):
    pulls = []
    for pull in repository.get_pulls(state="all"):
        formatted_pull = __retry_request(__format_pull, github_gmail, organization_name, repository, pull)
        pulls.append(formatted_pull)
    return pulls

def get_formatted_commits(repository, organization_name):
    formatted_commits = []
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        tmp_dir = pathlib.Path(tmp_dir_name)
        try:
            Repo.clone_from(repository.clone_url, f'{tmp_dir}')
        except GitError:
            log("WARNING", f"Likely already exists repo: {repository.name}")
        except Exception as e:
            log("ERROR", f"An exception occurred for Repo: {repository.name} {e}")

        try:
            repo_clone = Repo(tmp_dir)
            for commit in repo_clone.iter_commits():
                formatted_commits.append(__format_commit(organization_name, repository, commit))
        except Exception as e:
            log("ERROR", f"Failed to process commits for {repository.name}: {e}")
        finally:
            repo_clone.close()
            time.sleep(1)
    return formatted_commits

def get_formated_repository_data(repository: Repository, organization_name: str) -> tuple:
    readme = __get_readme(repository)
    created_at = __check_none(repository.created_at)
    updated_at = __check_none(repository.updated_at)
    pushed_at = __check_none(repository.pushed_at)
    cur_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        repository.fork
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
        repository.fork
    ]
    return repo_data, summary_data

def __retry_request(func: Callable, github_gmail: Github, *args, **kwargs):
    retries = 5
    while retries > 0:
        try:
            return func(*args, **kwargs)
        except RateLimitExceededException:
            wait_for_reset_ratelimit(github_gmail)
            retries -= 1
        except GithubException as e:
            if e.status == 403:
                return None
            raise
    log("ERROR", f"Failed {func.__name__} {5} times")
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

def __format_issue(repo_name:str, issue: Issue) -> list:
    user = issue.user
    return [
        repo_name,
        issue.title,
        issue.state,
        __check_none(issue.created_at),
        __check_none(issue.closed_at),
        user.email,
        user.login,
        user.name,
        user.id
    ]

def __format_branch(repo: Repository, branch: Branch) -> list:
    return [repo.name, branch.name, branch.protected, branch.last_modified]

def __format_contributors(organization_name: str, repository: Repository, contributor, error_message):
    if error_message != "":
        return [organization_name, repository.name, "ERROR", error_message, datetime.now()]

    return [organization_name, repository.name, contributor.author.login, contributor.total, datetime.now(), contributor.author.id]

def __format_user(repo: Repository, user: NamedUser) -> list:
    return [repo.name, repo.id, user.login, user.name, user.id, user.bio, user.blog, user.company,
     user.collaborators, __check_none(user.created_at), user.disk_usage, user.email, user.events_url,
     user.get_followers().totalCount, user.followers_url, user.get_following().totalCount,
     user.following_url, user.hireable, user.location, user.plan, user.public_repos, user.type,
     __check_none(user.updated_at), datetime.now().strftime("%Y-%m-%d %H:%M:%S")]

def __format_fork(organization_name: str, repo: Repository, fork: Repository, fork_owner: NamedUser, fork_owner_id: NamedUser, fork_owner_login:NamedUser, fork_subs: Repository, commits_ahead: int) -> list:
    return [organization_name, repo.name, fork.name, fork_owner_login, __check_none(fork.created_at),
                                              __check_none(fork.pushed_at), __check_none(fork.updated_at),
                                              datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fork_owner, fork_owner_id,
                                              fork.has_downloads, fork.last_modified_datetime, fork.watchers_count,
                                              fork_subs, fork.open_issues_count, commits_ahead]

def __format_pull(organization_name: str, repo: Repository, pull: PullRequest) -> list:
    return [organization_name, repo.name, pull.id, pull.additions, pull.deletions, pull.changed_files, pull.comments,
     pull.state, pull.merged, __check_none(pull.created_at), __check_none(pull.updated_at),
     __check_none(pull.closed_at), __check_none(pull.merged_at), pull.user.name, pull.user.login, pull.user.id,
     pull.last_modified, pull.assignee, pull.assignees, pull.comments, pull.title, pull.merge_commit_sha]

def __format_commit(organization_name: str, repo: Repository, commit: Commit) -> list:
    return [organization_name, repo.name, repo.created_at.strftime("%Y-%m-%d %H:%M:%S"), commit.message,
     commit.author.name, commit.author.email, commit.committer.name, commit.committer.email,
     commit.stats.total["deletions"], commit.stats.total["insertions"],
     __format_timestamp(commit.authored_datetime),
     __format_timestamp(commit.authored_datetime),
     commit.stats.total["files"], commit.binsha]