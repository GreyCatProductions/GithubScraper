from queue import Empty, Queue
from threading import Thread
from typing import List
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
org_queue: Queue[tuple[str, int]] = Queue()

def prepare_tasks(organizations: List[str], tokens: list[Github]) -> List[OrgState]:
    for organization in organizations:
        org_queue.put((organization, 0))

    results: List[OrgState] = []

    threads = []

    for i in range(len(tokens)):
        t = Thread(target=_prepare_organization_task, args=((tokens[i], i, results)))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    
    print(f"All organization objects ready. Made {len(results)} / {len(organizations)} organization task objects successfully")
    return results


def _prepare_organization_task(token: Github, index: int, target: List[OrgState]):
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
            
            new_org_task: OrgState = OrgState(organization, repos)
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
