from threading import Semaphore, Lock
import time
import requests
from urllib.parse import urlparse
from Logger import get_logger, get_request_logger

log = get_logger(__name__)
request_logger = get_request_logger()

_original_send = requests.Session.send
_global_block_lock = Lock()
_global_blocked_until = 0.0
_rate_lock = Lock()
_second_window_start = time.time()
_minute_window_start = time.time()
_second_count = 0
_minute_count = 0

BLOCK_SECONDS = 70
MAX_CONCURRENT_REQUESTS = 5
WAIT_BELOW_PRIMARY_LIMIT = 100
MAX_REQUESTS_PER_MINUTE = 800 #api limit is 900
MAX_REQUESTS_PER_SECOND = 10 #theoretically its max requests per minute / 60

concurrent_sem: Semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)

def _is_github_request(url: str) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host == "github.com" or host.endswith(".github.com")

def _wait_if_blocked():
    global _global_blocked_until
    while True:
        with _global_block_lock:
            now = time.time()
            wait = _global_blocked_until - now
        if wait <= 0:
            return
        time.sleep(wait)

def _acquire_rate_slot():
    global _second_window_start, _minute_window_start, _second_count, _minute_count

    while True:
        sleep_for = 0.0
        now = time.time()
        with _rate_lock:
            if now - _second_window_start >= 1.0:
                _second_window_start = now
                _second_count = 0
            if now - _minute_window_start >= 60.0:
                _minute_window_start = now
                _minute_count = 0

            second_full = _second_count >= MAX_REQUESTS_PER_SECOND
            minute_full = _minute_count >= MAX_REQUESTS_PER_MINUTE

            if not second_full and not minute_full:
                _second_count += 1
                _minute_count += 1
                return

            if second_full:
                sleep_for = max((_second_window_start + 1.0) - now, 0.01)
            if minute_full:
                minute_sleep = max((_minute_window_start + 60.0) - now, 0.01)
                sleep_for = max(sleep_for, minute_sleep)

        time.sleep(sleep_for)

def _patched_send(self, request, **kwargs):
    global _global_blocked_until

    if not _is_github_request(request.url):
        return _original_send(self, request, **kwargs)

    _wait_if_blocked()
    _acquire_rate_slot()

    concurrent_sem.acquire()
    
    try:
        resp = _original_send(self, request, **kwargs)
    
        if resp.status_code not in {200, 202, 404}:
            log.warning(f"HTTP {request.method} {request.url} -> {resp.status_code}")
    finally:
        concurrent_sem.release()
    
    remaining_raw = resp.headers.get("X-RateLimit-Remaining")
    reset_time_raw = resp.headers.get("X-RateLimit-Reset")
    auth = request.headers.get("Authorization", "")
    token_hint = auth[-4:] if len(auth) >= 4 else "?"
    
    reset_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(reset_time_raw))) if reset_time_raw else "?"
    request_logger.info(
        f"HTTP {request.method} {request.url} -> {resp.status_code} | "
        f"token=...{token_hint} | "
        f"remaining={remaining_raw or '?'} | "
        f"reset={reset_dt} | "
        f"retry-after={resp.headers.get('retry-after', '-')} | "
        f"content-type={resp.headers.get('content-type', '-')} | "
        f"content-length={resp.headers.get('content-length', '-')}"
    )
    
    if remaining_raw is not None:
        try:
            remaining = int(remaining_raw)
            if remaining < WAIT_BELOW_PRIMARY_LIMIT:
                if reset_time_raw is not None:
                    try:
                        reset_time = int(reset_time_raw)   
                        offset = 60
                        sleep_time = max(reset_time - time.time() + offset, 0)
                        log.info(f"Sleeping for {sleep_time}s — tickets left = {remaining} / {WAIT_BELOW_PRIMARY_LIMIT} (token ...{token_hint})")
                        time.sleep(sleep_time)

                    except ValueError:
                        log.warning(f"Reset time (non-int): {reset_time_raw}")
        except ValueError:
            log.warning(f"RateLimit remaining header (non-int): {remaining_raw}")

    if resp.status_code == 403 or resp.status_code == 429: #same error codes for primary and secondary key. So taking expecting worst case of secondary exceeded
        with _global_block_lock:
            time_to_sleep_req = resp.headers.get("retry-after")
            
            time_to_sleep = BLOCK_SECONDS if not time_to_sleep_req else float(time_to_sleep_req) + 10
                
            new_block = time.time() + time_to_sleep
            if new_block > _global_blocked_until:
                _global_blocked_until = new_block
                log.warning(f"GLOBAL PAUSE for {time_to_sleep}s")

    return resp

def install():
    requests.Session.send = _patched_send
