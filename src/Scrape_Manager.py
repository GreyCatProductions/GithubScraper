import csv
from typing import List
import pandas as pd
import os
import traceback
import ColumnsMap as ColumnsMap
from Formaters import *
from Logger import log
import csv
from CustomExceptions import TokenException, GithubFetchException
from github.PaginatedList import PaginatedList
from github.Repository import Repository
from github import Github

csv.field_size_limit(100000000)
COMPARE_HEADER = "Repo_ID"


def write_csv(data, columns, filepath, sep=";"):
    try:
        df = pd.DataFrame(data, columns=columns)
        if os.path.exists(filepath):
            df.to_csv(filepath, mode="a", index=False, sep=sep, header=False)
        else:
            df.to_csv(filepath, mode="w", index=False, sep=sep, header=True)
    except Exception as e:
        print(f"Failed to create csv with columns: {columns}: " + str(e))


def get_already_scraped_repos_amount(presentRepo: PaginatedList[Repository], clone_directory_path: str):
    csv_path = os.path.join(clone_directory_path, "organization_repos.csv")
    if not os.path.exists(csv_path):
        return 0

    with open(csv_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file, delimiter=";")

        repos = sorted(presentRepo, key=lambda r: r.id)
        
        rows = list(reader)
        rows.sort(key=lambda r: int(r[COMPARE_HEADER]))
        
        offset = 0
        max_len = min(len(repos), len(rows))
        
        while offset < max_len:
            repo_id = repos[offset].id
            row_id = int(rows[offset][COMPARE_HEADER])

            if repo_id != row_id:
                return offset

            offset += 1

        return offset


def process_organization(
    organization_name: str, clone_directory_path: str, github: Github, thread_nr
):
    try:
        organization = get_organization(organization_name, github, thread_nr)
    except Exception as e:
        log(
            thread_nr,
            "WARNING",
            f"Failed to get organization {organization_name}! Token probably invalid! {e}",
        )
        raise TokenException("")

    if not organization:
        raise GithubFetchException(
            f"[Thread {thread_nr}] Failed to get organization from github."
        )

    repos: PaginatedList[Repository] = organization.get_repos(type="all")

    log(thread_nr, "INFO", f"{repos.totalCount} repos found")

    os.makedirs(clone_directory_path, exist_ok=True)

    log(thread_nr, "INFO", f"Checking if repos might get skipped")
    amount_to_skip = get_already_scraped_repos_amount(repos, clone_directory_path)
    if amount_to_skip > 0:
        log(thread_nr, "INFO", f"Skipping {amount_to_skip} repos as they already exist")

    for i, repository in enumerate(repos):
        if i < amount_to_skip:
            continue

        data = {
            "organization_repos": [],
            "issues": [],
            "branches": [],
            "repos": [],
            "users": [],
            "commits": [],
            "forks": [],
            "contributions": [],
            "pulls": [],
        }

        log(thread_nr, "INFO", f"Processing {repository.name} ({i}/{repos.totalCount})")
        try:

            repo_data, summary_data = get_formatted_repository_data(
                repository, organization_name, thread_nr
            )
            data["organization_repos"].append(repo_data)
            data["repos"].append(summary_data)
            data["issues"].extend(get_formatted_issues(repository, github, thread_nr))
            log(thread_nr, "INFO", "issues processed")
            data["branches"].extend(
                get_formatted_branches(repository, github, thread_nr)
            )
            log(thread_nr, "INFO", "branches processed")
            data["contributions"].extend(
                get_formatted_contributions(
                    repository, organization_name, github, thread_nr
                )
            )
            log(thread_nr, "INFO", "contributions processed")
            data["users"].extend(get_formatted_users(repository, github, thread_nr))
            log(thread_nr, "INFO", "users processed")
            data["forks"].extend(
                get_formatted_forks(repository, organization_name, github, thread_nr)
            )
            log(thread_nr, "INFO", "forks processed")
            data["pulls"].extend(
                get_formatted_pulls(repository, organization_name, github, thread_nr)
            )
            log(thread_nr, "INFO", "pulls processed")
            # data["commits"].extend(get_formatted_commits(repository, organization_name, thread_nr))
            # log(thread_nr,"INFO", "commits processed")

            log(
                thread_nr,
                "INFO",
                f"Finished processing {repository.name} of organization {organization_name}.",
            )

            for key, columns in ColumnsMap.COLUMNS_MAP.items():
                csv_file = os.path.join(clone_directory_path, f"{key}.csv")
                write_csv(data[key], columns, csv_file)

        except RateLimitExceededException:
            wait_for_reset_ratelimit(thread_nr, github)
            continue
        except Exception as e:
            log(
                thread_nr,
                "ERROR",
                "Error on repository: " + repository.name + " " + str(e),
            )
            print(traceback.print_exc())
            continue
    return True
