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
from schema.ThreadTasks import OrgState, RepoState
from Formaters import get_organization
from TaskPreparer import prepare_tasks

csv.field_size_limit(100000000)

PATH_TO_ORGANIZATIONS = Path("~/GithubScraper/organizations.txt").expanduser()
MAX_RETRIES_PER_ORG = 5
MAX_THREADS_PER_ORG = 3

retries_lock = Lock()

org_tasks: List[OrgState] = []

def worker(github: Github, token_id: int):
    while True:
        for org_task in org_tasks:
            if org_task.get_activate_workers_snapshot() < MAX_THREADS_PER_ORG:
                repo, repostate = org_task.get_available_repo()
                if not repo or not repostate:
                    continue
                
                org_task.acquire_slot()
                
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
    
    org_tasks = prepare_tasks(organizations, github_tokens) #blocking, uses all available threads to fetch repos and only add the ones that are not already processed
    
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
