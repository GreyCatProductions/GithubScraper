import time
from typing import Callable

from github import Github, GithubException, RateLimitExceededException

from Logger import get_logger

log = get_logger(__name__)


def retry_request(func: Callable, github_gmail: Github, scraper_nr, *args, **kwargs):
    retries = 5
    while retries > 0:
        try:
            return func(*args, **kwargs)
        except RateLimitExceededException:
            _wait_for_reset_ratelimit(github_gmail)
            retries -= 1
        except GithubException as e:
            if e.status == 403:
                log.error(f"Access denied for {func.__name__}")
                return None
            raise
    log.error(f"Failed {func.__name__} {5} times")
    return None

def _wait_for_reset_ratelimit(g: Github):
    reset_time = g.rate_limiting_resettime
    current_time = time.time()
    offset = 300
    sleep_time = reset_time - current_time + offset

    log.info(f"Ratelimit reached! Reset_time = {reset_time}, Current_time = {current_time}, Time to sleep = {sleep_time}")

    retries = 3

    while retries > 0:
        if sleep_time > 0:
            log.info(f"Sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        if g.get_rate_limit().rate.remaining >= 4900:
            log.info("Rate limit successfully reset")
            return True
        else:
            log.warning(f"Rate limit failed to reset. Should be 5000 but is {g.get_rate_limit().rate.remaining}! Retrying...")
            retries -= 1
            time.sleep(300)

    log.error("Failed to reset rate limit. Waiting for 65 minutes as emergency solution!")
    time.sleep(65 * 60)
    return True

