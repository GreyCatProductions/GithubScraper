import threading
import time
import requests

_original_send = requests.Session.send
_block_lock = threading.Lock()
_blocked_until = 0.0
MAX_RETRIES_403 = 5
BLOCK_SECONDS = 70

def _wait_if_blocked():
    global _blocked_until
    while True:
        with _block_lock:
            now = time.time()
            wait = _blocked_until - now
        if wait <= 0:
            return
        time.sleep(wait)

def _patched_send(self, request, **kwargs):
    global _blocked_until

    _wait_if_blocked()

    print("HTTP:", request.method, request.url)
    resp = _original_send(self, request, **kwargs)
    print(" ->", resp.status_code)

    if resp.status_code == 403:
        with _block_lock:
            new_block = time.time() + BLOCK_SECONDS
            if new_block > _blocked_until:
                _blocked_until = new_block
                print(f"GLOBAL PAUSE for {BLOCK_SECONDS}s")

    return resp

    return resp
def install():
    requests.Session.send = _patched_send