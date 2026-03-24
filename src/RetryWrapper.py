from typing import Callable
from Logger import get_logger

log = get_logger(__name__)


def retry_request(func: Callable, *args, **kwargs):
    return func(*args, **kwargs) #with the new approach the request wrapper already catches all possible TimeExceeded exceptions
