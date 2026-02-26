from dataclasses import dataclass, field
from enum import Enum
from threading import Lock, Semaphore
from typing import List, Tuple
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from github.PaginatedList import PaginatedList
from github.Repository import Repository

class Status(Enum):
    AVAILABLE = "available"
    DOING = "doing"
    DONE = "done"

@dataclass(frozen=True, slots=True)
class RepoState:
    retry_count: int = 0
    state: Status = Status.AVAILABLE


@dataclass(slots=True)
class OrgState:
    organization: Organization | NamedUser | AuthenticatedUser
    repos: PaginatedList[Repository]
    repo_tasks: List[RepoState] = field(init=False)
    _sem: Semaphore = field(init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    active_workers: int = 0
    retries: int = 0
    
    def __post_init__(self) -> None:
        self._sem = Semaphore(1)
        self.repo_tasks = [RepoState()] * self.repos.totalCount

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
        
    def get_activate_workers_snapshot(self) -> int:
        with self._lock:
            return self.active_workers
    
    def get_available_repo(self) -> Tuple[Repository | None, RepoState | None]:
        with self._lock:
            for i in range(len(self.repo_tasks)):
                repo_task = self.repo_tasks[i]
                if repo_task.state == Status.AVAILABLE:
                    return (self.repos[i], repo_task)
                
            return None, None
