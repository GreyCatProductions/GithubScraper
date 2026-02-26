import os
from pathlib import Path
import traceback
from typing import Dict, List
from Logger import log
from Rate_Limiter import wait_for_reset_ratelimit
from Scrape_Manager import process_repo
from threading import Lock, Thread
from queue import Empty, Queue
from github import Github, RateLimitExceededException
from github.Repository import Repository
from GitHubTokenReader import get_tokens
import csv
from schema.ThreadTasks import OrgState, RepoTask
from Formaters import get_organization
from TaskPreparer import prepare_tasks

csv.field_size_limit(100000000)

PATH_TO_ORGANIZATIONS = Path("../organizations.txt")
MAX_RETRIES_PER_ORG = 5
MAX_THREADS_PER_ORG = 3
PATH_TO_GITHUB_DATA = Path("../github_data")

retries_lock = Lock()

org_tasks: List[OrgState] = []

def worker(github: Github, token_id: int):
    while True:
        for org_task in org_tasks:
            if org_task.get_activate_workers_snapshot() < MAX_THREADS_PER_ORG:
                repo, repoTask, index = org_task.claim_available_repo() #lock happens automatically if not None returned
                if not repo or not repoTask:
                    continue
                
                repoTask.thread_id = token_id
                retries = repoTask.retry_count
                repoTask.github = github
                save_path: Path = org_task.org_path
                
                org_task.acquire_slot()
                
                while True:
                    try:
                        process_repo(repo, repoTask, save_path)
                    except RateLimitExceededException:
                        wait_for_reset_ratelimit(token_id, github)
                        continue
                    except Exception as e:
                        log(
                            token_id,
                            "ERROR",
                            "Unexpected Error on repository: " + repo.name + " " + str(e),
                        )
                        print(traceback.print_exc())
                        continue
                    
                org_task.release_slot()

def load_organizations() -> List[str]:
    with open(PATH_TO_ORGANIZATIONS, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def main():
    github_tokens: list[Github] = [Github(token) for token in get_tokens()]
    available_tokens = len(github_tokens)
    print(f"Loaded {available_tokens} tokens.")
    
    organizations = load_organizations()
    print(f"Loaded {len(organizations)} organizations.")
    
    org_tasks = prepare_tasks(organizations, github_tokens, PATH_TO_GITHUB_DATA) #blocking, uses all available threads to fetch repos and only add the ones that are not already processed
    
    threads = []

    for i in range(len(github_tokens)):
        t = Thread(target=worker, args=((github_tokens[i], i)))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
        
    print("All organizations processed.")


if __name__ == "__main__":
    main()
