import csv
import pandas as pd
import os
import traceback
import Columns_Maper
from Formaters import *
from Logger import log

def write_csv(data, columns, filepath, sep=';'):
    try:
        df = pd.DataFrame(data, columns=columns)
        if os.path.exists(filepath):
            df.to_csv(filepath, mode='a', index=False, sep=sep, header=False)
        else:
            df.to_csv(filepath, mode='w', index=False, sep=sep, header=True)
    except Exception as e:
        print(f"Failed to create csv with columns: {columns}")

def get_already_scraped_repos_amount(clone_directory_path):
    if not os.path.exists(os.path.join(clone_directory_path, 'organization_repos.csv')):
        return 0

    csv_path = os.path.join(clone_directory_path, 'organization_repos.csv')
    with open(csv_path, mode='r', encoding='utf-8', errors="replace") as file:
        reader = list(csv.reader(file, delimiter=';'))
        row_count = len(reader)
    return row_count - 1

def process_organization(organization_name: str, clone_directory_path: str, github_gmail, thread_nr):
    organization = get_organization(organization_name, github_gmail, thread_nr)
    repos = organization.get_repos(type="all")

    log(thread_nr, "INFO", f"{repos.totalCount} repos found")

    columns_map = Columns_Maper.get_columns_map()

    os.makedirs(clone_directory_path, exist_ok=True)

    amount_to_skip = get_already_scraped_repos_amount(clone_directory_path)
    if amount_to_skip > 0:
        log(thread_nr, "INFO", f"Skipping {amount_to_skip} repos as they already exist")

    for i, repository in enumerate(repos):
        if i < amount_to_skip:
            continue

        data = {"organization_repos": [], "issues": [], "branches": [], "repos": [], "users": [],
                "commits": [], "forks": [], "contributions": [], "pulls": []}


        log(thread_nr, "INFO", f"Processing {repository.name} ({i}/{repos.totalCount})")
        try:
            start_requests = github_gmail.get_rate_limit().core.remaining

            repo_data, summary_data = get_formated_repository_data(repository, organization_name)
            data["organization_repos"].append(repo_data)
            data["repos"].append(summary_data)
            data["issues"].extend(get_formatted_issues(repository, github_gmail, thread_nr))
            #log(scraper_nr,"INFO", "issues processed")
            data["branches"].extend(get_formatted_branches(repository, github_gmail, thread_nr))
            #log(scraper_nr,"INFO", "branches processed")
            data["contributions"].extend(get_formatted_contributions(repository, organization_name, github_gmail, thread_nr))
            #log(scraper_nr,"INFO", "contributions processed")
            data["users"].extend(get_formatted_users(repository, github_gmail, thread_nr))
            #log(scraper_nr,"INFO", "users processed")
            data["forks"].extend(get_formatted_forks(repository, organization_name, github_gmail, thread_nr))
            #log(scraper_nr,"INFO", "forks processed")
            data["pulls"].extend(get_formatted_pulls(repository, organization_name, github_gmail, thread_nr))
            #log(scraper_nr,"INFO", "pulls processed")
            data["commits"].extend(get_formatted_commits(repository, organization_name, thread_nr))
            #log(scraper_nr,"INFO", "commits processed")

            end_requests = github_gmail.get_rate_limit().core.remaining
            costed_requests = start_requests - end_requests
            log(thread_nr, "INFO", f"Finished processing {repository.name}. Request cost = {costed_requests}, Left = {end_requests}")


            for key, columns in columns_map.items():
                csv_file = os.path.join(clone_directory_path, f"{key}.csv")
                write_csv(data[key], columns, csv_file)

            if end_requests < 100:
                wait_for_reset_ratelimit(thread_nr, github_gmail)

        except RateLimitExceededException:
            wait_for_reset_ratelimit(thread_nr, github_gmail)
            continue
        except Exception as e:
            log(thread_nr, "ERROR", "Error on repository: " + repository.name + " " + str(e))
            print(traceback.print_exc())
            continue