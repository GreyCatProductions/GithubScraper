import pandas as pd
import os
import traceback
from Formaters import *
from Logger import log

def write_csv(data, columns, filepath, sep=";"):
    df = pd.DataFrame(data, columns=columns)
    df.to_csv(filepath, index=False, sep=sep)
    log("INFO", f"Saved CSV file: {filepath}")

def process_organization(organization_name: str, clone_directory_path: str, github_gmail):
    organization = get_organization(organization_name, github_gmail)

    repos = organization.get_repos(type="all")
    data = {"organization_repos": [], "issues": [], "branches": [], "repos": [], "users": [],
            "commits": [], "forks": [], "contributions": [], "pulls": []}

    for i, repository in enumerate(repos):
        log("INFO", f"Processing {repository.name} ({i}/{repos.totalCount})")

        try:
            repo_data, summary_data = get_formated_repository_data(repository, organization_name)
            data["organization_repos"].append(repo_data)
            data["repos"].append(summary_data)
            data["issues"].extend(get_formatted_issues(repository, github_gmail))
            log("INFO", "issues processed")
            data["branches"].extend(get_formatted_branches(repository, github_gmail))
            log("INFO", "branches processed")
            data["contributions"].extend(get_formatted_contributions(repository, organization_name, github_gmail))
            log("INFO", "contributions processed")
            data["users"].extend(get_formatted_users(repository, github_gmail))
            log("INFO", "users processed")
            data["forks"].extend(get_formatted_forks(repository, organization_name, github_gmail))
            log("INFO", "forks processed")
            data["pulls"].extend(get_formatted_pulls(repository, organization_name, github_gmail))
            log("INFO", "pulls processed")
            data["commits"].extend(get_formatted_commits(repository, organization_name))
            log("INFO", "commits processed")

            log("INFO", f"Finished processing {repository.name}")
            break
        except RateLimitExceededException:
            wait_for_reset_ratelimit(github_gmail)
            continue
        except Exception as e:
            log("ERROR", "Error on repository: " + repository.name + " " + str(e))
            print(traceback.print_exc())
            continue

    columns_mapping = {
    "organization_repos": ['Organization', 'RepoName', 'Repo_ID', 'Forks_Count', 'Stargazers_Count', 'Watchers_Count',
                         'Size', 'Open_Issues_Count', 'Subscribers_Count', 'Network_Count', 'Language', 'Description',
                         'Pushed_at', 'Created_at', 'Updated_at', 'Date', 'Default_Branch', "readme", "Fork_Bool"],

    "repos": ['Organization', 'RepoName', 'Repo Author', 'Created_at', 'Size', 'Stargazers_Url',
                    'Stargazers_Count', 'Subscribers', 'Subscribers_Count', 'Forks', 'Forks_Count', 'Forks_Url',
                    'Language', 'Description', 'Created at', 'Updated at', 'Date', "Fork_Bool"],

    "issues": ["Repository", "Issue_Title", "Issue_State",
                       "Created At", "Closed Date", "User Email", "User Login", "User Name", "User ID"],

    "branches": ["Repo Name", "Branch Name", "Protected", "Last Modified"],

    "contributions": ['Organization', 'Repository', 'Username', 'Contributions', 'Date', "Contributor Login"],

    "users": ['Repo Name', "Repo ID", 'Login', 'Name', 'ID', 'Bio', 'Blog', 'Company', 'Collaborators',
                    'Created at', 'Disk Usage', 'Email', 'Events Url', 'Followers', 'Followers Url', 'Following',
                    'Following Url', 'Hireable', 'Location', 'Plan', 'Public repos', 'type', 'Updated at', 'Date'],

    "forks": ['Organization', 'RepoName', 'ForkName', 'Fork Author Login', 'Created at', 'Pushed at', 'Updated at',
                    'Date', "Fork Author Name", "Fork Author ID", "Fork Downloads", "Fork Last Modified", "Fork Watchers",
                    "Fork Subscribers", "Fork Open Issues", "Commits Ahead"],

    "pulls": ["Orga", "Repository", "ID", "Additions", "Deletions", "Changed_Files", "Comments", "State",
                     "Merged", "Created_at", "Updated_at", "Closed_at", "Merged_at", "Pull Username", "Pull User Login",
                     "Pull User ID", "Pull Last Modified", "Pull Assignee", "Pull Assignees", "Pull Comments",
                     "Pull Title", "Commit SHA"],

    "commits": ['Organization', 'RepoName', 'Repo Created at', 'Commit Message', 'Author Name', "Author Email",
                      'Committer Name', "Commiter Email", 'Deletions', 'Additions', 'Commit Date',
                      'Authored Date', "Files Modified", "BinSHA"]
    }

    os.makedirs(clone_directory_path, exist_ok=True)
    for key, columns in columns_mapping.items():
        csv_file = os.path.join(clone_directory_path, f"{key}.csv")
        write_csv(data[key], columns, csv_file)