
from RequestLimiter import install
install() #must be before github imports

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
from tqdm import tqdm

csv.field_size_limit(100000000)

PATH_TO_ORGANIZATIONS = Path("../organizations.txt")
MAX_THREADS_PER_ORG = 12
MAX_RETRIES_PER_REPO = 5
PATH_TO_GITHUB_DATA = Path("../github_data")

retries_lock = Lock()

orgTasks: List[OrgSmartTask] = []

def handle_org_task(repo: Repository, repoTask: RepoTask, orgTask: OrgSmartTask, token_id: int, github: Github, pbar: tqdm):
    repoTask.thread_id = token_id
    repoTask.github = github
    save_path: Path = orgTask.org_path
    
    orgTask.acquire_slot()
    try:
        while True:
            try:
                process_repo(repo, repoTask, save_path)
                repoTask.complete()
                pbar.update(1)
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
                    pbar.update(1)
                    break
    
    except Exception as e:
        log(token_id, "ERROR", f"Unexpected error while handling repo {repo.name}!")
        return
    finally:
        orgTask.release_slot()

def worker(github: Github, token_id: int, pbar: tqdm):
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
        
        handle_org_task(repo, repoTask, orgTask, token_id, github, pbar)

def load_organizations() -> List[str]:
    with open(PATH_TO_ORGANIZATIONS, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def main():
    github_tokens: list[Github] = [Github(token) for token in get_tokens()]
    available_tokens = len(github_tokens)
    if available_tokens <= 0:
        raise Exception("No tokens loaded!")
    
    print(f"Loaded {available_tokens} tokens.")
    
    organizations = load_organizations()
    print(f"Loaded {len(organizations)} organizations.")
    
    global orgTasks
    orgTasks = prepare_tasks(organizations, github_tokens, PATH_TO_GITHUB_DATA) #blocking, uses all available threads to fetch repos and only add the ones that are not already processed

    total_repos = sum(orgTask.repos.totalCount - orgTask.offset for orgTask in orgTasks)

    threads = []

    with tqdm(total=total_repos, unit="repo", desc="Scraping") as pbar:
        for i in range(len(github_tokens)):
            t = Thread(target=worker, args=((github_tokens[i], i, pbar)))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
        
    print("All organizations processed.")


if __name__ == "__main__":
    main()
