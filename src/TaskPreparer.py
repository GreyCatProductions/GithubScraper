import csv
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import sleep
from typing import List
from github import Github
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from Formaters import get_organization
from Logger import get_logger
from schema.ThreadTasks import OrgSmartTask
from github.PaginatedList import PaginatedList
from github.Repository import Repository

log = get_logger(__name__)

MAX_RETRIES_PER_ORG = 5
COMPARE_HEADER = "Repo_ID"

def prepare_tasks(organizations: List[str], tokens: list[Github], path_to_github_data: Path) -> List[OrgSmartTask]:
    org_queue: Queue[tuple[str, int]] = Queue()
    
    for organization in organizations:
        org_queue.put((organization, 0))

    results: List[OrgSmartTask] = []

    threads = []

    for i in range(len(tokens)):
        t = Thread(target=_prepare_organization_task, args=((tokens[i], i, results, path_to_github_data, org_queue)))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    
    log.info(f"All organization objects ready. Made {len(results)} / {len(organizations)} organization task objects successfully")
    return results

def _get_already_scraped_repos_amount(presentRepo: PaginatedList[Repository], org_save_path):
    csv_path = os.path.join(org_save_path, "organization_repos.csv")
    if not os.path.exists(csv_path):
        return 0

    with open(csv_path, mode="r", encoding="utf-8") as file:
        scraped_ids: set[int] = {int(row[COMPARE_HEADER]) for row in csv.DictReader(file, delimiter=";")}

    count = 0
    for repo in presentRepo:   
        if repo.id in scraped_ids:
            count += 1
        else:
            break
    return count



def _prepare_organization_task(token: Github, index: int, target: List[OrgSmartTask], 
                               path_to_github_data: Path, org_queue: Queue[tuple[str, int]] = Queue()):
    while True:
        try:
            org, tries = org_queue.get_nowait()
        except Empty:
            break

        try:
            log.info( f"Fetching repositories from: {org}")
            organization: Organization | NamedUser | AuthenticatedUser | None = (
                get_organization(org, token, index))
            if not organization:
                raise Exception("Returned organization is null!")
            
            repos: PaginatedList[Repository] = organization.get_repos(type="all")
            if not repos:
                raise Exception(f"Failed to get repos for {org}!")
            
            path = path_to_github_data / org
            os.makedirs(path, exist_ok=True)

            log.info( f"Checking if repos for {org} might get skipped")
            amount_to_skip = _get_already_scraped_repos_amount(repos, path)
            if amount_to_skip > 0:
                log.info( f"Skipping {amount_to_skip} repos as they already exist")
                
            new_org_task: OrgSmartTask = OrgSmartTask(organization=organization, repos=repos, offset=amount_to_skip, org_path=path)
            target.append(new_org_task)
            log.info( f"Successfully fetched repos and prepared task object for: {org}")
            
        except Exception as e:
            if tries < MAX_RETRIES_PER_ORG:
                log.warning(f"Retry {tries}/{MAX_RETRIES_PER_ORG} for {org}: {e}")
                sleep(3)
                org_queue.put((org, tries + 1))
            else:
                log.error(f"Giving up on {org} after {MAX_RETRIES_PER_ORG} retries: {e}")
        finally:
            org_queue.task_done()
