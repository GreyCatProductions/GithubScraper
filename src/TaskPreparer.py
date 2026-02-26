import csv
import itertools
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Iterable, List
from github import Github
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from Formaters import get_organization
from Logger import log
from schema.ThreadTasks import OrgState
from github.PaginatedList import PaginatedList
from github.Repository import Repository

MAX_RETRIES_PER_ORG = 3
COMPARE_HEADER = "Repo_ID"
org_queue: Queue[tuple[str, int]] = Queue()

def prepare_tasks(organizations: List[str], tokens: list[Github], path_to_github_data: Path) -> List[OrgState]:
    for organization in organizations:
        org_queue.put((organization, 0))

    results: List[OrgState] = []

    threads = []

    for i in range(len(tokens)):
        t = Thread(target=_prepare_organization_task, args=((tokens[i], i, results, path_to_github_data)))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    
    print(f"All organization objects ready. Made {len(results)} / {len(organizations)} organization task objects successfully")
    return results

def _get_already_scraped_repos_amount(presentRepo: PaginatedList[Repository], clone_directory_path: str):
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


def _prepare_organization_task(token: Github, index: int, target: List[OrgState], path_to_github_data: Path):
    while True:
        try:
            org, tries = org_queue.get_nowait()
        except Empty:
            break

        try:
            log(index, "INFO", f"Fetching repositories from: {org}")
            organization: Organization | NamedUser | AuthenticatedUser = (
                get_organization(org, token, index)
            )
            if not organization:
                raise Exception("Returned organization is null!")
            
            repos: PaginatedList[Repository] = organization.get_repos(type="all")
            if not repos:
                raise Exception(f"Failed to get repos for {org}!")
            
            path = os.path(path_to_github_data} + {org}")
            os.makedirs(path, exist_ok=True)

            log(index, "INFO", f"Checking if repos for {org} might get skipped")
            amount_to_skip = _get_already_scraped_repos_amount(repos, path)
            if amount_to_skip > 0:
                log(index, "INFO", f"Skipping {amount_to_skip} repos as they already exist")
                
            new_org_task: OrgState = OrgState(organization=organization, repos=repos, offset=amount_to_skip, org_path=org_path)
            target.append(new_org_task)
            log(index, "INFO", f"Successfully fetched repos and prepared task object for: {org}")
            
        except Exception as e:
            if tries < MAX_RETRIES_PER_ORG:
                log(
                    index,
                    "WARNING",
                    f"Retry {tries}/{MAX_RETRIES_PER_ORG} for {org}: {e}",
                )
                
                org_queue.put((org, tries + 1))
            else:
                log(
                    index,
                    "ERROR",
                    f"Giving up on {org} after {MAX_RETRIES_PER_ORG} retries: {e}",
                )
        finally:
            org_queue.task_done()
