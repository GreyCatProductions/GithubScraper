import os

from github import Github
from tqdm import tqdm
from Logger import log
from Rate_Limiter import wait_for_reset_ratelimit
from Scrape_Manager import process_organization

def main():
    github_gmail = Github("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") # gmail.com

    organizations = ["amzn", "groupon"]
    # Übrige microsfot
    # NASA: https://github.com/NASA
    # ESA: https://github.com/ESA
    # DLR: https://github.com/DLR-SC
    # CNES: CNES (French National Centre for Space Studies)
    # ISRO: https://github.com/orgs/isro/repositories
    # JAXA: https://github.com/jaxa UK Space Agency: https://github.com/UKSpaceAgency
    for organization_to_process in tqdm(organizations):
        if github_gmail.rate_limiting[0] < 500:
            wait_for_reset_ratelimit(github_gmail)

        log("INFO", f" Processing: {organization_to_process}")
        path = "./github_data/" + organization_to_process
        os.makedirs(path, exist_ok=True)
        folder_path = os.listdir(path)

        if not folder_path or len(folder_path) != sum(1 for i in folder_path if i.endswith(".csv")):
            process_organization(organization_to_process, path, github_gmail)
        else:
            print(organization_to_process + " already scraped successfully. Skipping ...")

main()