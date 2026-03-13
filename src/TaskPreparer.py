import csv
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import sleep
from typing import List, Set
from github import Github
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from Formaters import get_organization
from Logger import get_logger
from schema.ThreadTasks import OrgSmartTask, RepoTask
from github.PaginatedList import PaginatedList
from github.Repository import Repository

log = get_logger(__name__)

MAX_RETRIES_PER_ORG = 5
COMPARE_HEADER = "Repo_ID"


def prepare_tasks(
    organization_names: List[str], tokens: list[Github], path_to_github_data: Path
) -> List[OrgSmartTask]:
    org_queue: Queue[tuple[str, int]] = Queue()

    for name in organization_names:
        org_queue.put((name, 0))

    results: List[OrgSmartTask] = []

    threads = []

    for i in range(len(tokens)):
        t = Thread(
            target=_prepare_organization_task,
            args=(tokens[i], results, path_to_github_data, org_queue),
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    log.info(
        f"All organization objects ready. Made {len(results)} / {len(organization_names)} organization task objects successfully"
    )
    return results


def _prepare_organization_task(
    token: Github,
    target: List[OrgSmartTask],
    path_to_github_data: Path,
    org_queue: Queue[tuple[str, int]],
):
    while True:
        try:
            org, tries = org_queue.get_nowait()
        except Empty:
            break

        try:
            log.info(f"Preparing task object for: {org}")

            org_path = path_to_github_data / org
            os.makedirs(org_path, exist_ok=True)

            repo_ids: Set[int] = _get_repo_id_set(org, token)
            tasks: List[RepoTask] = [
                RepoTask(id=repo_id) for repo_id in sorted(repo_ids)
            ]

            counter: int = _complete_already_finished_tasks(tasks=tasks, org_path=org_path)
            
            new_org_task: OrgSmartTask = OrgSmartTask(repo_tasks=tasks, org_path=org_path)
            
            target.append(new_org_task)
            log.info(
                f"Successfully fetched {len(repo_ids)} repo ids, automatically completed {counter} of them as their id already exists in save and prepared task object for: {org}"
            )

        except Exception as e:
            if tries < MAX_RETRIES_PER_ORG:
                log.warning(f"Retry {tries}/{MAX_RETRIES_PER_ORG} for {org}: {e}")
                sleep(3)
                org_queue.put((org, tries + 1))
            else:
                log.error(
                    f"Giving up on {org} after {MAX_RETRIES_PER_ORG} retries: {e}"
                )
        finally:
            org_queue.task_done()


def _get_repo_id_set(org: str, token: Github) -> Set[int]:
    organization: Organization | NamedUser | AuthenticatedUser | None = (
        get_organization(org, token)
    )
    if not organization:
        raise Exception("Returned organization is null!")

    repo_iter: PaginatedList[Repository] = organization.get_repos(type="all")
    if not repo_iter:
        raise Exception(f"Failed to get repos for {org}!")

    repo_id_set: Set[int] = set()  # snapshot of all repo ids
    for repo in repo_iter:
        repo_id_set.add(repo.id)

    return repo_id_set

def _complete_already_finished_tasks(tasks: List[RepoTask], org_path: Path) -> int:
    csv_path = os.path.join(org_path, "organization_repos.csv")
    counter = 0

    log.info(f"Checking if {csv_path} exists")
    if os.path.exists(csv_path):
        with open(csv_path, mode="r", encoding="utf-8") as file:
            scraped_ids: Set[int] = {
                int(row[COMPARE_HEADER])
                for row in csv.DictReader(file, delimiter=";")
            }
        
        log.info(f"Found {len(scraped_ids)} already existing organization repo ids")

        for task in tasks:
            if task.id in scraped_ids:
                task.complete()
                counter += 1
                
    return counter