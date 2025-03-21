import time
from datetime import datetime


def wait_for_reset_ratelimit(g):
    print("Rate Limit Reached")
    print(g.rate_limiting)

    retries = 3

    while retries > 0:
        reset_time = datetime.fromtimestamp(g.rate_limiting_resettime)
        now = datetime.now()
        diff = (reset_time - now).total_seconds()
        offset_time = 30

        print(f"Sleeping for {diff + offset_time:.2f} seconds")

        if diff > 0:
            time.sleep(diff + offset_time)

        if g.rate_limiting[0] == 5000:
            print("Rate limit successfully reset")
            return True
        else:
            print("Rate limit failed to reset. Retrying...")
            retries -= 1
            time.sleep(10)
    Exception("Failed to reset rate limit")
