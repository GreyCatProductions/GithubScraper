import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from github import Github
from Logger import log
from Rate_Limiter import wait_for_reset_ratelimit
from Scrape_Manager import process_organization
from GitHubTokenReader import get_tokens


def scrape_organization(organization, github_gmail, scraper_nr):
    if github_gmail.rate_limiting[0] < 500:
        wait_for_reset_ratelimit(github_gmail)

    log(scraper_nr, "INFO", f"Processing: {organization}")
    path = f"./github_data/{organization}"
    os.makedirs(path, exist_ok=True)
    process_organization(organization, path, github_gmail, scraper_nr)


def main():
    organizations = ["amzn", "groupon"]
    github_gmails = [Github(token) for token in get_tokens()]
    threads_to_create = min(len(organizations), len(github_gmails))
    print(f"Creating {threads_to_create} threads")

    scraper_nr = 1

    with ThreadPoolExecutor(threads_to_create) as executor:
        future_to_org = {}

        for i, org in enumerate(organizations):
            scraper_nr = i + 1
            github_gmail = github_gmails[i % len(github_gmails)]
            future = executor.submit(scrape_organization, org, github_gmail, scraper_nr)
            future_to_org[future] = org

        for future in as_completed(future_to_org):
            try:
                future.result()
            except Exception as e:
                log(scraper_nr, "ERROR", f"Error processing {future_to_org[future]}: {e}")

if __name__ == "__main__":
    main()