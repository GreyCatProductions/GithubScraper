import csv
from pathlib import Path
from threading import Semaphore
import pandas as pd
import os
import schema.ColumnsMap as ColumnsMap
from Formaters import *
from github.Repository import Repository
from github import Github
from schema.ThreadTasks import RepoTask
from Logger import get_logger

log = get_logger(__name__)

csv.field_size_limit(100000000)
csv_lock: Semaphore = Semaphore(1)

def write_csv(data, columns, filepath, sep=";"):
    with csv_lock:
        try:
            df = pd.DataFrame(data, columns=columns)
            if os.path.exists(filepath):
                df.to_csv(filepath, mode="a", index=False, sep=sep, header=False)
            else:
                df.to_csv(filepath, mode="w", index=False, sep=sep, header=True)
        except Exception as e:
            log.error(f"Failed to create csv with columns: {columns}: " + str(e))


def process_repo(github: Github, repo_task: RepoTask, path: Path):
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

    repository: Repository = github.get_repo(repo_task.id)
    org_name: str = str(repository.owner.login)

    log.info(f"Processing repo {repository.name} | org={org_name}")

    repo_data, summary_data = get_formatted_repository_data(
        repository, org_name
    )
    data["organization_repos"].append(repo_data)
    data["repos"].append(summary_data)
    data["issues"].extend(get_formatted_issues(repository))
    log.info("issues processed")
    data["branches"].extend(get_formatted_branches(repository))
    log.info("branches processed")
    data["contributions"].extend(get_formatted_contributions(repository, org_name))
    log.info("contributions processed")
    data["users"].extend(get_formatted_users(repository))
    log.info("users processed")
    data["forks"].extend(
        get_formatted_forks(repository, org_name)
    )
    log.info("forks processed")
    data["pulls"].extend(
        get_formatted_pulls(repository, org_name)
    )
    log.info("pulls processed")
    data["commits"].extend(get_formatted_commits(repository, org_name))
    log.info("commits processed")

    log.info(f"Finished processing {repository.name} of organization {org_name}.")

    for key, columns in ColumnsMap.COLUMNS_MAP.items():
        csv_file = os.path.join(path, f"{key}.csv")
        write_csv(data[key], columns, csv_file)
