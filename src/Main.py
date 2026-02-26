from pathlib import Path
from typing import List
from github.Repository import Repository
from Logger import log
from Scrape_Manager import process_repo
from threading import Lock, Thread
from github import Github
from GitHubTokenReader import get_tokens
import csv
from schema.ThreadTasks import OrgSmartTask, RepoTask
from TaskPreparer import prepare_tasks

csv.field_size_limit(100000000)

PATH_TO_ORGANIZATIONS = Path("../organizations.txt")
MAX_THREADS_PER_ORG = 3
MAX_RETRIES_PER_REPO = 3
PATH_TO_GITHUB_DATA = Path("../github_data")

retries_lock = Lock()

orgTasks: List[OrgSmartTask] = []

def handle_org_task(repo: Repository, repoTask: RepoTask, orgTask: OrgSmartTask, token_id: int, github: Github):
    repoTask.thread_id = token_id
    repoTask.github = github
    save_path: Path = orgTask.org_path
    
    orgTask.acquire_slot()
    try:
        while True:
            try:
                process_repo(repo, repoTask, save_path)
                repoTask.complete()
                break
            except Exception as e:
                log(
                    token_id,
                    "ERROR",
                    f"[Retry {repoTask.retry_count} / {MAX_RETRIES_PER_REPO}] Unexpected Error on repository: " + repo.name + " " + str(e),
                )
                
                repoTask.retry_count += 1
                if repoTask.retry_count >= MAX_RETRIES_PER_REPO:
                    log(
                    token_id,
                    "ERROR",
                    f"repository: " + repo.name + "reached max amount of retries. Killing it",
                    )
                    repoTask.kill()
                    break
    
    except Exception as e:
        log(token_id, "ERROR", f"Unexpected error while handling repo {repo.name}!")
        return
    finally:
        orgTask.release_slot()

def worker(github: Github, token_id: int):
    while True:
        repo, repoTask, orgTask = None, None, None
        for iterOrgTask in orgTasks:
            if iterOrgTask.get_activate_workers_snapshot() < MAX_THREADS_PER_ORG:
                repo, repoTask, index = iterOrgTask.claim_available_repo() #lock happens automatically if not None returned
                if not repo or not repoTask:
                    continue
                
                orgTask = iterOrgTask
                break
                
        if not repo or not repoTask or not orgTask: 
            log(token_id, "INFO", "Could not find any task to do. Disabling")
            return
        
        handle_org_task(repo, repoTask, orgTask, token_id, github)

def load_organizations() -> List[str]:
    with open(PATH_TO_ORGANIZATIONS, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def main():
    github_tokens: list[Github] = [Github(token) for token in get_tokens()]
    available_tokens = len(github_tokens)
    print(f"Loaded {available_tokens} tokens.")
    
    organizations = load_organizations()
    print(f"Loaded {len(organizations)} organizations.")
    
    global orgTasks
    orgTasks = prepare_tasks(organizations, github_tokens, PATH_TO_GITHUB_DATA) #blocking, uses all available threads to fetch repos and only add the ones that are not already processed

    
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
