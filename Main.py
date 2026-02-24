import os

from Logger import log
from Scrape_Manager import process_organization
import threading
from queue import Queue
from github import Github
from GitHubTokenReader import get_tokens
import csv
csv.field_size_limit(100000000)


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

            Token_Valid = process_organization(org, path, github_gmail, token_id)
            if not Token_Valid:
                return
        except Exception as e:
            log(token_id, "ERROR", f"Error processing {org}: {e}")
        finally:
            org_queue.task_done()


def main():
    #organizations = [
    #"apache",
    #"aws",
    #"AWSLABS",
    #"azure",
    #"cloudflare",
    #"facebook",
    #"GoogleCloudPlatform",
    #"oracle"
    #]
    # 13.02.2026 JSIS
    organizations = [
        "GoogleCloudPlatform", "googlechrome", "android", "azure", "tencentcloud", "slackhq",
        "SAP", "intuit", "servicenow", "paloaltonetworks", "shopify", "fortinet", "workday",
        "autodesk", "zoom", "veeva", "docusign", "crowdstrike", "atlassian", "snowflake-labs",
        "cloudflare", "datadog", "hubspot", "tyler-technologies", "samsara",
        "magento", "NaverCloudPlatform", "palantir", "ROBLOX", "nginx", "pinterest" # Additions 17.02.
        "ibm-cloud" # Additions 19.02.2026
        "adobe", "MoneyLion", "ansys", "ibm-cloud", "aws", "aliyun", "opentelekomcloud", # Additions 20.02.2026
        "officedev", "netease-in", "indeedeng", "payu", "fiware" # Additions 24.02.2026
    ] # Finished seit 20.: ansys, palantir, ibm-cloud, aliyun, shopify

    # 30.01.2026
    #organizations = ["bigcommerce", "Unity-Technologies", "contentful", "figma", "miroapp", "mapbox", "stripe", "square", "plaid", "Adyen", "postmanlabs", "coinbase", "binance", "android", "apple", "odoo", "drupal", "joomla",
    #                 "woocommerce", "PrestaShop", "magento", "medusajs", "saleor", "huggingface", "solana"]
    # Vorher
    # organizations = ['usatoday', 'wsj', 'nytimes', 'datadesk', 'nydailynews', 'washingtonpost', 'newyorkpost', 'newsapps', 'Houston-Chronicle', 'dallasmorningnews', 'dallasnews', 'sfchronicle', 'newsdaycom', 'bostonglobe', 'Arizona-Republic-Data', 'njam-data', 'ajcnews', 'MinneapolisStarTribune', 'phillymedia', 'Detroit-Free-Press', 'TheOregonian', 'tbtimes', 'MiamiHerald', 'sdut-datadesk', 'postdispatchinteractive', 'denverpost', 'Baltimore-Sun', 'OrlandoSentinel', 'datahub', 'SunSentinel', 'seattletimes', 'sa-express-news', 'courierjournal', 'buffalo-news', 'owh-projects', 'hartfordcourant', 'pioneerpress', 'statesman', 'palmbeachpost', 'mcclatchy-southeast', 'lohud', 'sltrib']

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