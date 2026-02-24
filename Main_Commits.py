#!/usr/bin/env python3
r"""
main_commits.py - FIXED for Windows path limits + Better Error Handling
────────────────────────────────────────────────────────────────────
Scrapes commit data by cloning repositories locally.
Designed to run in parallel with main.py (which uses the GitHub API).

IMPROVEMENTS:
- Better default branch detection with fallback methods
- Progress logging during commit iteration
- Verification that branches have commits before processing
- Enhanced error messages and debugging info
- Timeout detection via periodic logging

Usage:
  python main_commits.py                     # uses default 6 workers
  python main_commits.py --workers 4         # limit to 4 parallel clones
  python main_commits.py --poll              # keep polling for new repos
"""

import argparse
import csv
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
from threading import Lock

from git import Repo as GitRepo
from git.exc import GitError, GitCommandError

import Columns_Maper
from Logger import log
from Scrape_Manager import write_csv

csv.field_size_limit(100_000_000)

# Organisation list (keep in sync with main.py)
ORGANIZATIONS = [
    "GoogleCloudPlatform", "googlechrome", "android", "azure", "tencentcloud", "slackhq",
    "SAP", "intuit", "servicenow", "paloaltonetworks", "shopify", "fortinet", "workday",
    "autodesk", "zoom", "veeva", "docusign", "crowdstrike", "atlassian", "snowflake-labs",
    "cloudflare", "datadog", "hubspot", "tyler-technologies", "samsara",
    "magento", "NaverCloudPlatform", "palantir", "ROBLOX", "nginx", "pinterest"  # Additions 17.02.
                                                                    "ibm-cloud"  # Additions 19.02.2026
                                                                    "adobe", "MoneyLion", "ansys", "ibm-cloud", "aws",
    "aliyun", "opentelekomcloud",  # Additions 20.02.2026
    "officedev", "netease-in", "indeedeng", "payu", "fiware"  # Additions 24.02.2026

]
GITHUB_DATA_ROOT = "./github_data"
COMMIT_COLUMNS = Columns_Maper.get_columns_map()["commits"]

# Use very short temp path on D: to avoid Windows 260-char limit
TEMP_ROOT = r"D:\\t"

# Lock for writing to the same CSV from multiple threads
_csv_meta_lock = Lock()
_csv_locks: dict[str, Lock] = {}


def _get_csv_lock(org: str) -> Lock:
    with _csv_meta_lock:
        if org not in _csv_locks:
            _csv_locks[org] = Lock()
        return _csv_locks[org]


def get_discovered_repos(org: str) -> list[dict]:
    """Return a list of {'name': ..., 'clone_url': ...} from organization_repos.csv."""
    csv_path = os.path.join(GITHUB_DATA_ROOT, org, "organization_repos.csv")
    if not os.path.exists(csv_path):
        return []

    repos = []
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            repo_name = row.get("RepoName", "").strip()
            org_name = row.get("Organization", org).strip()
            created_at = row.get("RepoCreatedAt", "").strip()
            if repo_name:
                clone_url = f"https://github.com/{org_name}/{repo_name}.git"
                repos.append({
                    "name": repo_name,
                    "organization": org_name,
                    "clone_url": clone_url,
                    "created_at": created_at
                })
    return repos


def get_already_processed_repos(org: str) -> set[str]:
    """Return set of repo names that already have commits in commits.csv."""
    csv_path = os.path.join(GITHUB_DATA_ROOT, org, "commits.csv")
    if not os.path.exists(csv_path):
        return set()

    processed = set()
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name = row.get("RepoName", "").strip()
            if name:
                processed.add(name)
    return processed


def format_commit(organization_name: str, repo_name: str, repo_created_at: str, commit) -> list:
    """Format a single gitpython commit into a row matching COMMIT_COLUMNS."""
    author_name = getattr(commit.author, "name", None) or ""
    author_email = getattr(commit.author, "email", None) or ""
    committer_name = getattr(commit.committer, "name", None) or ""
    committer_email = getattr(commit.committer, "email", None) or ""
    authored_dt = commit.authored_datetime.strftime("%Y-%m-%d %H:%M:%S")
    committed_dt = commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S")

    # gitpython's diff stats
    stats = commit.stats.total
    deletions = stats.get("deletions", 0)
    insertions = stats.get("insertions", 0)
    files_modified = stats.get("files", 0)

    return [
        organization_name,
        repo_name,
        repo_created_at,
        commit.message,
        author_name,
        author_email,
        "",  # Author Login (not available from local clone)
        committer_name,
        committer_email,
        "",  # Committer Login (not available from local clone)
        deletions,
        insertions,
        committed_dt,
        authored_dt,
        files_modified,
        commit.binsha.hex(),
    ]


def _get_default_branch_ref(repo_clone, worker_id: int, repo_full_name: str) -> str:
    """
    Get the default branch ref with better error handling and verification.
    Returns ref like 'refs/remotes/origin/main' or 'refs/remotes/origin/master'.
    """
    # Method 1: Try symbolic-ref (most reliable when origin/HEAD is set)
    try:
        ref = repo_clone.git.symbolic_ref("refs/remotes/origin/HEAD").strip()
        # Verify this ref actually exists and has commits
        try:
            list(repo_clone.iter_commits(ref, max_count=1))
            log(worker_id, "DEBUG", f"{repo_full_name}: Found default via symbolic-ref: {ref}")
            return ref
        except Exception as e:
            log(worker_id, "DEBUG", f"{repo_full_name}: symbolic-ref returned {ref} but verification failed: {e}")
    except Exception as e:
        log(worker_id, "DEBUG", f"{repo_full_name}: symbolic-ref failed: {e}")

    # Method 2: Try common defaults (main, master)
    for candidate in ["refs/remotes/origin/main", "refs/remotes/origin/master"]:
        try:
            list(repo_clone.iter_commits(candidate, max_count=1))
            log(worker_id, "DEBUG", f"{repo_full_name}: Using fallback branch: {candidate}")
            return candidate
        except Exception:
            continue

    # Method 3: List all remote branches and pick the first one with commits
    try:
        remote_refs = repo_clone.remote().refs
        remote_branches = [ref for ref in remote_refs if ref.name != 'origin/HEAD']
        log(worker_id, "DEBUG", f"{repo_full_name}: Available branches: {[r.name for r in remote_branches[:10]]}")

        for ref in remote_branches:
            try:
                # Check if branch has at least one commit
                list(repo_clone.iter_commits(ref, max_count=1))
                log(worker_id, "INFO", f"{repo_full_name}: Using first available branch: {ref.name}")
                return ref.name
            except Exception:
                continue
    except Exception as e:
        log(worker_id, "DEBUG", f"{repo_full_name}: Could not list remote branches: {e}")

    raise ValueError("Could not determine default branch")


def process_repo_commits(org: str, repo_info: dict, worker_id: int) -> int:
    r"""
    Clone a single repo WITHOUT checkout, extract commits from default branch.
    This avoids Windows path limits while getting the same commit data as the original.
    """
    repo_name = repo_info["name"]
    clone_url = repo_info["clone_url"]
    org_name = repo_info["organization"]
    repo_full_name = f"{org_name}/{repo_name}"
    created_at = repo_info.get("created_at", "")
    csv_path = os.path.join(GITHUB_DATA_ROOT, org, "commits.csv")

    commit_rows = []

    # Use very short temp path: D:\\t\\<8-char-hash>
    os.makedirs(TEMP_ROOT, exist_ok=True)
    short_hash = hashlib.md5(f"{org_name}_{repo_name}_{time.time()}".encode()).hexdigest()[:8]
    clone_dest = os.path.join(TEMP_ROOT, short_hash)

    repo_clone = None
    total_commits = 0

    try:
        log(worker_id, "INFO", f"Cloning {repo_full_name} ...")
        start_time = time.time()

        # Clone WITHOUT checkout to avoid Windows path limit errors
        repo_clone = GitRepo.clone_from(clone_url, clone_dest, no_checkout=True)
        clone_time = time.time() - start_time
        log(worker_id, "INFO", f"{repo_full_name}: Clone completed in {clone_time:.1f}s")

        # Get the default branch ref with improved detection
        try:
            default_ref = _get_default_branch_ref(repo_clone, worker_id, repo_full_name)
            log(worker_id, "INFO", f"{repo_full_name}: Walking {default_ref}")
        except ValueError as e:
            log(worker_id, "WARNING", f"{repo_full_name}: {e}")
            return 0

        # Verify the branch has commits before starting iteration
        try:
            test_commits = list(repo_clone.iter_commits(default_ref, max_count=1))
            if not test_commits:
                log(worker_id, "WARNING", f"{repo_full_name}: Branch {default_ref} has no commits")
                return 0
        except Exception as e:
            log(worker_id, "ERROR", f"{repo_full_name}: Cannot iterate {default_ref}: {e}")
            return 0

        # Start commit iteration with progress logging
        log(worker_id, "INFO", f"{repo_full_name}: Starting commit iteration...")
        last_log_time = time.time()
        iteration_start = time.time()

        for commit in repo_clone.iter_commits(default_ref):
            try:
                commit_rows.append(format_commit(org_name, repo_name, created_at, commit))
                total_commits += 1

                # Log progress every 5000 commits or every 30 seconds
                current_time = time.time()
                if total_commits % 5000 == 0 or (current_time - last_log_time > 30):
                    elapsed = current_time - iteration_start
                    rate = total_commits / elapsed if elapsed > 0 else 0
                    # log(worker_id, "INFO", f"{repo_full_name}: {total_commits} commits ({rate:.1f}/s)...")
                    last_log_time = current_time

                # Write in chunks to avoid holding large repos in memory
                if len(commit_rows) >= 1000:
                    lock = _get_csv_lock(org)
                    with lock:
                        write_csv(commit_rows, COMMIT_COLUMNS, csv_path)
                    commit_rows.clear()

            except Exception as e:
                log(worker_id, "WARNING", f"{repo_full_name}: Error formatting commit {commit.hexsha[:8]}: {e}")
                continue

        # Write any remaining commits
        if commit_rows:
            lock = _get_csv_lock(org)
            with lock:
                write_csv(commit_rows, COMMIT_COLUMNS, csv_path)
            commit_rows.clear()

        total_time = time.time() - start_time
        log(worker_id, "INFO", f"Completed {repo_full_name}: {total_commits} commits in {total_time:.1f}s")
        return total_commits

    except GitCommandError as e:
        log(worker_id, "ERROR", f"{repo_full_name} GitCommandError: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            log(worker_id, "ERROR", f"{repo_full_name} stderr: {e.stderr[:800]}")
        return 0
    except GitError as e:
        log(worker_id, "WARNING", f"Git error for {repo_full_name}: {e}")
        return 0
    except KeyboardInterrupt:
        log(worker_id, "WARNING", f"Interrupted while processing {repo_full_name}")
        raise
    except Exception as e:
        log(worker_id, "ERROR", f"Error processing commits for {repo_full_name}: {e}")
        import traceback
        log(worker_id, "ERROR", f"Traceback: {traceback.format_exc()[:1000]}")
        return 0
    finally:
        if repo_clone is not None:
            try:
                repo_clone.close()
            except:
                pass
            del repo_clone
        time.sleep(0.5)

        # Clean up temp dir
        try:
            if os.path.exists(clone_dest):
                shutil.rmtree(clone_dest, ignore_errors=True)
        except Exception as e:
            log(worker_id, "WARNING", f"Could not clean up {clone_dest}: {e}")


def gather_all_pending() -> list[tuple[str, dict]]:
    """Return a flat list of (org, repo_info) for all repos not yet processed."""
    all_pending = []
    for org in ORGANIZATIONS:
        discovered = get_discovered_repos(org)
        if not discovered:
            continue
        already_done = get_already_processed_repos(org)
        pending = [r for r in discovered if r["name"] not in already_done]
        if pending:
            log(0, "INFO", f"[{org}] {len(pending)}/{len(discovered)} repos pending")
        for repo in pending:
            all_pending.append((org, repo))
    return all_pending


def main():
    parser = argparse.ArgumentParser(description="Scrape commits by cloning repos locally.")
    parser.add_argument("--workers", type=int, default=6,
                        help="Number of parallel git-clone workers (default: 6)")
    parser.add_argument("--poll", action="store_true",
                        help="Keep polling for newly discovered repos every 5 min")
    parser.add_argument("--poll-interval", type=int, default=300,
                        help="Seconds between poll cycles (default: 300)")
    args = parser.parse_args()

    log(0, "INFO", f"Starting commit scraper with {args.workers} workers.")
    log(0, "INFO", f"Temp directory: {TEMP_ROOT}")

    # Configure git for long paths on Windows (one-time setup)
    log(0, "INFO", "Configuring git for Windows long paths...")
    try:
        subprocess.run(["git", "config", "--global", "core.longpaths", "true"],
                       check=False, capture_output=True, timeout=10)
        log(0, "INFO", "Git configuration complete.")
    except Exception as e:
        log(0, "WARNING", f"Could not configure git: {e}")

    while True:
        all_pending = gather_all_pending()

        if not all_pending:
            log(0, "INFO", "No pending repos found.")
            if not args.poll:
                break
            log(0, "INFO", f"Sleeping {args.poll_interval}s before next poll ...")
            time.sleep(args.poll_interval)
            continue

        log(0, "INFO", f"{len(all_pending)} total repos to process across all orgs.")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(process_repo_commits, org, repo, i % args.workers): (org, repo)
                for i, (org, repo) in enumerate(all_pending)
            }
            with tqdm(total=len(all_pending), desc="All repos", unit="repo",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} repos [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
                for future in as_completed(futures):
                    org, repo = futures[future]
                    try:
                        count = future.result()
                        pbar.set_postfix_str(f"{org}/{repo['name']} ({count} commits)")
                    except KeyboardInterrupt:
                        log(0, "WARNING", "Interrupted by user. Shutting down...")
                        pool.shutdown(wait=False, cancel_futures=True)
                        raise
                    except Exception as e:
                        pbar.set_postfix_str(f"{org}/{repo['name']} FAILED")
                        log(0, "ERROR", f"[{org}] {repo['name']} failed: {e}")
                    pbar.update(1)

        if not args.poll:
            break

        log(0, "INFO", f"Poll cycle complete. Sleeping {args.poll_interval}s before next check ...")
        time.sleep(args.poll_interval)

    log(0, "INFO", "All organisations processed. Done.")


if __name__ == "__main__":
    main()
