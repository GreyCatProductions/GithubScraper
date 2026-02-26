from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Lock, Semaphore
from typing import List, Tuple
from github import Github
from github.Organization import Organization
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from github.PaginatedList import PaginatedList
from github.Repository import Repository

class Status(Enum):
    AVAILABLE = "available"
    DOING = "doing"
    DONE = "done"

@dataclass(slots=True)
class RepoTask:
    organization: Organization | NamedUser | AuthenticatedUser
    thread_id: int = -1 #what thread works on me
    retry_count: int = 0 #how many retries happened
    _state: Status = Status.AVAILABLE #what state
    github: Github | None = None


@dataclass(slots=True)
class OrgState:
    organization: Organization | NamedUser | AuthenticatedUser
    repos: PaginatedList[Repository]
    offset: int
    org_path: Path
    _repo_tasks: List[RepoTask] = field(init=False)
    _sem: Semaphore = field(init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    _activate_workers: int = 0
    _retries: int = 0
    
    def __post_init__(self) -> None:
        self._sem = Semaphore(1)
        self._repo_tasks = [RepoTask(organization=self.organization) for _ in range(self.repos.totalCount)]
        for i in range(self.offset):
            self._repo_tasks[i]._state = Status.DONE

    def acquire_slot(self) -> None:
        self._sem.acquire()
        with self._lock:
            self._activate_workers += 1

    def release_slot(self) -> None:
        with self._lock:
            self._activate_workers -= 1
        self._sem.release()

    def add_retry(self, n: int = 1) -> None:
        with self._lock:
            self._retries += n

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            return self._activate_workers, self._retries
        
    def get_activate_workers_snapshot(self) -> int:
        with self._lock:
            return self._activate_workers
    
    def claim_available_repo(self) -> Tuple[Repository | None, RepoTask | None, int | None]:
        with self._lock:
            for i in range(self.offset, len(self._repo_tasks)):
                repo_task = self._repo_tasks[i]
                if repo_task._state == Status.AVAILABLE:
                    repo_task._state = Status.DOING
                    return (self.repos[i], repo_task, i)
                
            return None, None, None
