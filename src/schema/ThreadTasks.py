from dataclasses import dataclass, field
from threading import Lock, Semaphore
from typing import List
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from github.PaginatedList import PaginatedList
from github.Repository import Repository

@dataclass(frozen=True, slots=True)
class RepoTask:
    org: str
    repo_id: int
    retry_count: int


@dataclass(slots=True)
class OrgState:
    organization: Organization | NamedUser | AuthenticatedUser
    max_workers: int
    repos: PaginatedList[Repository]
    _sem: Semaphore = field(init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    active_workers: int = 0
    retries: int = 0

    def __post_init__(self) -> None:
        self._sem = Semaphore(self.max_workers)

    def acquire_slot(self) -> None:
        self._sem.acquire()
        with self._lock:
            self.active_workers += 1

    def release_slot(self) -> None:
        with self._lock:
            self.active_workers -= 1
        self._sem.release()

    def add_retry(self, n: int = 1) -> None:
        with self._lock:
            self.retries += n

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            return self.active_workers, self.retries
