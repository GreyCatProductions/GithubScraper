from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Dict, List, Set, Tuple
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
    KILLED = "killed" #if done but not done properly

@dataclass(slots=True)
class RepoTask:
    id: int
    retry_count: int = 0 #how many retries happened
    _state: Status = Status.AVAILABLE #what state

    def complete(self):
        self._state = Status.DONE
        
    def kill(self):
        self._state = Status.KILLED


@dataclass(slots=True)
class OrgSmartTask:
    org_path: Path
    repo_tasks: List[RepoTask] #sorted by id
    
    _lock: Lock = field(default_factory=Lock, init=False)
    _activate_workers: int = 0
    _retries: int = 0
    
    def acquire_slot(self) -> None:
        with self._lock:
            self._activate_workers += 1

    def release_slot(self) -> None:
        with self._lock:
            self._activate_workers -= 1

    def add_retry(self, n: int = 1) -> None:
        with self._lock:
            self._retries += n

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            return self._activate_workers, self._retries
        
    def get_activate_workers_snapshot(self) -> int:
        with self._lock:
            return self._activate_workers
    
    def claim_available_repo_task(self) -> RepoTask | None:
        with self._lock:
            for repo_task in self.repo_tasks:
                if repo_task._state == Status.AVAILABLE:
                    repo_task._state = Status.DOING
                    return repo_task
                
            return None
