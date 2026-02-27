import time
from github import Github
from Logger import log

def wait_for_reset_ratelimit(thread: int, g: Github):
    reset_time = g.rate_limiting_resettime
    current_time = time.monotonic()
    offset = 300
    sleep_time = reset_time - time.monotonic() + offset

    log(thread, "INFO", f"Ratelimit reached! Reset_time = {reset_time}, Current_time = {current_time}, Time to sleep = {sleep_time}")

    retries = 3

    while retries > 0:
        if sleep_time > 0:
            print(f"Sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        if g.get_rate_limit().rate.remaining >= 4900:
            print("Rate limit successfully reset")
            return True
        else:
            print(f"Rate limit failed to reset. Should be 5000 but is {g.get_rate_limit().rate.remaining}! Retrying...")
            retries -= 1
            time.sleep(300)

    log(thread, "ERROR", "Failed to reset rate limit. Waiting for 65 minutes as emergency solution!")
    time.sleep(65 * 60)
    return True
