import os
from pathlib import Path
from typing import Dict, List
from Logger import log
from Scrape_Manager import process_organization
from threading import Lock, Thread
from queue import Empty, Queue
from github import Github
from github.Repository import Repository
from GitHubTokenReader import get_tokens
import csv
from CustomExceptions import TokenException, GithubFetchException
from schema.ThreadTasks import OrgState, RepoTask
from Formaters import get_organization
from TaskPreparer import prepare_tasks

csv.field_size_limit(100000000)

PATH_TO_ORGANIZATIONS = Path("~/GithubScraper/organizations.txt").expanduser()
MAX_RETRIES_PER_ORG = 5

retries_lock = Lock()

org_tasks: List[OrgState] = []

def token_worker(github: Github, org_queue: Queue[tuple[str, int]], token_id: int):
    while True:
        try:
            org, attempt = org_queue.get_nowait()
        except Empty:
            break

        try:
            log(token_id, "INFO", f"Starting to scrape organization: {org}")

            path = f"../github_data/{org}"

            os.makedirs(path, exist_ok=True)

            process_organization(org, path, github, token_id)

        except TokenException:
            log(token_id, "ERROR", "Shutting down this thread; token likely dead")
            org_queue.put((org, attempt + 1))
            return

        except GithubFetchException as e:
            if attempt <= MAX_RETRIES_PER_ORG:
                log(
                    token_id,
                    "WARNING",
                    f"Retry {attempt}/{MAX_RETRIES_PER_ORG} for {org}: {e}",
                )
                org_queue.put((org, attempt + 1))
            else:
                log(
                    token_id,
                    "ERROR",
                    f"Giving up on {org} after {MAX_RETRIES_PER_ORG} retries: {e}",
                )

        except Exception as e:
            if attempt <= MAX_RETRIES_PER_ORG:
                log(
                    token_id,
                    "ERROR",
                    f"Unexpected error for {org}, retrying ({attempt}/{MAX_RETRIES_PER_ORG}): {e}",
                )
                org_queue.put((org, attempt + 1))
            else:
                log(
                    token_id,
                    "ERROR",
                    f"Unexpected error for {org}, giving up after {MAX_RETRIES_PER_ORG}: {e}",
                )

        finally:
            org_queue.task_done()


def load_organizations() -> List[str]:
    with open(PATH_TO_ORGANIZATIONS, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def main():
    github_tokens: list[Github] = [Github(token) for token in get_tokens()]
    available_tokens = len(github_tokens)
    print(f"Loaded {available_tokens} tokens.")
    
    organizations = load_organizations()
    print(f"Loaded {len(organizations)} organizations.")
    
    org_tasks = prepare_tasks(organizations, github_tokens) #blocking, uses all available threads to fetch repos

    print("All organizations processed.")


if __name__ == "__main__":
    main()
