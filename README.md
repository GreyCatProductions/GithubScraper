# GithubScraper

A multi-threaded tool for bulk-scraping GitHub organization data into CSV files using the GitHub API.

## What it does

Give it a list of GitHub organizations and it will collect the following data for every repository in each org:

| CSV file | Contents |
|---|---|
| `organization_repos.csv` | Repo metadata (stars, forks, language, license, README, etc.) |
| `repos.csv` | Repo summary with author and URL info |
| `issues.csv` | Issues with state, dates, and user info |
| `branches.csv` | Branch names, protection status, and last modified date |
| `commits.csv` | Full commit history with author/committer details |
| `contributions.csv` | Per-user contribution counts per repo |
| `users.csv` | Collaborator profiles |
| `forks.csv` | Fork details including divergence (commits ahead/behind) |
| `pulls.csv` | Pull requests with diff stats and merge info |

Output is organized as `github_data/<org_name>/<data>.csv`.

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Create a `.env` file** based on `.env_example`
```env
GITHUB_TOKENS=ghp_token1,ghp_token2,ghp_token3
ORGANIZATIONS=org1,org2,org3
```

- `GITHUB_TOKENS` — one or more [GitHub personal access tokens](https://github.com/settings/tokens), comma-separated. Each token maps to one worker thread.
- `ORGANIZATIONS` — GitHub organization or user names to scrape, comma-separated.

**3. Run**
```bash
cd src
python Main.py
```

## How it works

- One worker thread is spawned per token, so adding more tokens increases parallelism.
- A certain amount threads can work on the same organization concurrently (defaults to 12) (`MAX_THREADS_PER_ORG`).
- Each repo is retried several times on failure (defaults to 5) before being skipped.
- Resumable: already-scraped repos are detected by comparing existing `organization_repos.csv` against live repo IDs and skipped automatically.
- Auto Regulating Wrapper for requests package handles all requests called to github. Default 
settings are defensive and might be improved for better performance

## Requirements

- Python 3.12+
- See `requirements.txt` for package dependencies
