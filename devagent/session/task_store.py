"""In-memory background task registry (Phase 14)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

TaskStatus = Literal["running", "done", "failed"]


@dataclass
class BackgroundTask:
    task_id: str
    label: str
    status: TaskStatus = "running"
    result: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at


class TaskStore:
    """Thread-safe in-memory registry of background agent tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()

    def add(self, task_id: str, label: str) -> BackgroundTask:
        bt = BackgroundTask(task_id=task_id, label=label)
        with self._lock:
            self._tasks[task_id] = bt
        return bt

    def complete(self, task_id: str, result: str, *, failed: bool = False) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.status = "failed" if failed else "done"
                task.result = result
                task.finished_at = time.time()

    def list_tasks(self) -> list[BackgroundTask]:
        with self._lock:
            return list(self._tasks.values())

    def get(self, task_id: str) -> BackgroundTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def clear_done(self) -> int:
        """Remove finished tasks. Returns the count removed."""
        with self._lock:
            done = [tid for tid, t in self._tasks.items() if t.status != "running"]
            for tid in done:
                del self._tasks[tid]
        return len(done)


# Process-level singleton
_global_store = TaskStore()


def get_store() -> TaskStore:
    """Return the global task store shared across the process."""
    return _global_store
