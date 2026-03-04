from RequestLimiter import install
install() #must be before github imports

import logging  
from pathlib import Path
from typing import List
from github.Repository import Repository
from Logger import get_logger, setup_logging
from ScrapeManager import process_repo
from threading import Lock, Thread
from github import Github
import csv
from schema.ThreadTasks import OrgSmartTask, RepoTask
from TaskPreparer import prepare_tasks
from tqdm import tqdm
from dotenv import load_dotenv
import os

MAX_THREADS_PER_ORG = 12
MAX_RETRIES_PER_REPO = 5
PATH_TO_GITHUB_DATA = Path("../github_data")

load_dotenv()
setup_logging(level=logging.INFO) 
csv.field_size_limit(100000000)

log = get_logger(__name__)

orgTasks: List[OrgSmartTask] = []

def handle_org_task(repoTask: RepoTask, orgTask: OrgSmartTask, github: Github, pbar: tqdm):
    save_path: Path = orgTask.org_path
    orgTask.acquire_slot()
    
    try:
        while True:
            try:
                process_repo(github, repoTask, save_path)
                repoTask.complete()
                pbar.update(1)
                break
            except Exception as e:
                repoTask.retry_count += 1
                log.error(f"[Retry {repoTask.retry_count} / {MAX_RETRIES_PER_REPO}] Unexpected Error on repository: " + str(repoTask.id) + " " + str(e),)
                
                if repoTask.retry_count >= MAX_RETRIES_PER_REPO:
                    log.error(f"repository: " + str(repoTask.id) + " reached max amount of retries. Killing it",)
                    repoTask.kill()
                    pbar.update(1)
                    break
    
    except Exception as e:
        log.error(f"Unexpected error while handling repo {str(repoTask.id)}!")
        return
    finally:
        orgTask.release_slot()

def worker(github: Github, pbar: tqdm):
    while True:
        repoTask, orgTask = None, None
        for iterOrgTask in orgTasks:
            if iterOrgTask.get_activate_workers_snapshot() < MAX_THREADS_PER_ORG:
                repoTask: RepoTask | None = iterOrgTask.claim_available_repo_task() #lock happens automatically if not None returned
                if not repoTask:
                    continue
                
                orgTask = iterOrgTask
                break
                
        if not repoTask or not orgTask: 
            log.info("Could not find any task to do. Shuting down")
            return
        
        handle_org_task(repoTask, orgTask, github, pbar)

def main():
    tokens_raw = os.getenv("GITHUB_TOKENS", "")
    organizations_raw = os.getenv("ORGANIZATIONS", "")
    tokens_list = [t.strip() for t in tokens_raw.split(",") if t.strip()]
    organizations = [org.strip() for org in organizations_raw.split(",") if org.strip()]
    githubs: list[Github] = [Github(token, per_page=100) for token in tokens_list]
    available_tokens = len(githubs)
    if available_tokens <= 0:
        raise Exception("No tokens loaded!")
    
    log.info(f"Loaded {available_tokens} tokens.")
    log.info(f"Loaded {len(organizations)} organizations.")
    
    global orgTasks
    orgTasks = prepare_tasks(organizations, githubs, PATH_TO_GITHUB_DATA) #blocking, uses all available threads to fetch repos and only add the ones that are not already processed

    total_repos = sum(len(orgTask.repo_tasks) for orgTask in orgTasks)

    threads = []

    with tqdm(total=total_repos, unit="repo", desc="Scraping") as pbar:
        for i in range(len(githubs)):
            t = Thread(target=worker, args=((githubs[i], pbar)))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
        
    log.info("All organizations processed. Finishing")


if __name__ == "__main__":
    main()
