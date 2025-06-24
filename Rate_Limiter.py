import time
from datetime import datetime

def wait_for_reset_ratelimit(g):
    print("Rate Limit Reached")
    print(g.rate_limiting)

    retries = 3

    while retries > 0:
        reset_time = datetime.fromtimestamp(g.rate_limiting_resettime)
        now = datetime.now()
        diff = abs((reset_time - now).total_seconds())
        offset_time = 30

        if diff > 0:
            print(f"Sleeping for {diff + offset_time:.2f} seconds")
            time.sleep(diff + offset_time)
        else:
            print(f"Reset time already passed ({diff:.2f}s ago), checking again in 10s")
            time.sleep(10)

        if g.rate_limiting[0] >= 4900:
            print("Rate limit successfully reset")
            return True
        else:
            print("Rate limit failed to reset. Retrying...")
            retries -= 1
            time.sleep(300)

    raise Exception("Failed to reset rate limit")
