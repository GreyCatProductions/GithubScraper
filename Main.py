import os

from Logger import log
from Scrape_Manager import process_organization
import threading
from queue import Queue
from github import Github
from GitHubTokenReader import get_tokens


def token_worker(github_gmail: Github, org_queue: Queue[str], token_id: int):
    while not org_queue.empty():
        try:
            org = org_queue.get_nowait()
        except:
            break

        try:
            log(token_id, "INFO", f"Starting to scrape organization: {org}")

            path = f"./github_data/{org}"
            os.makedirs(path, exist_ok=True)

            process_organization(org, path, github_gmail, token_id)
        except Exception as e:
            log(token_id, "ERROR", f"Error processing {org}: {e}")
        finally:
            org_queue.task_done()


def main():
    organizations = [
        "ebay", "SAP", "allegro", "zalando", "otto-de", "walmartlabs",
        "vinted", "jd-opensource", "rakutentech", "myntra", "flipkart",
        "namshi", "salesforce", "mozilla-firefox", "google", "APPLE",
        "bytedance", "grab", "spotify", "nextcloud", "otto-de", "mercadolibre",
        "etsy", "revolut-engineering"
    ]

    org_queue: Queue[str] = Queue()
    for org in organizations:
        org_queue.put(org)

    github_gmails: list[Github] = [Github(token) for token in get_tokens()]
    num_workers = len(github_gmails)

    threads = []

    for i in range(num_workers):
        t = threading.Thread(target=token_worker, args=(github_gmails[i], org_queue, i))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print("All organizations processed.")


if __name__ == "__main__":
    main()
