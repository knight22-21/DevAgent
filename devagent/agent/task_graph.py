"""Phase 9 — Task graph for multi-agent orchestration.

The coordinator decomposes a user task into a directed acyclic graph of
subtasks.  Each node knows its dependencies, its worker type, and its
execution status.  The graph resolves topological waves of parallel work:
all tasks whose dependencies are satisfied form a single parallel wave.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from devagent.session import store

WorkerType = Literal["implementer", "tester", "reviewer"]
TaskStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class TaskNode:
    id: str
    description: str
    worker_type: WorkerType = "implementer"
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = "pending"
    result: str = ""
    output_files: list[str] = field(default_factory=list)
    assigned_session: str = ""

    @staticmethod
    def make(
        description: str,
        worker_type: WorkerType = "implementer",
        depends_on: list[str] | None = None,
    ) -> TaskNode:
        return TaskNode(
            id=str(uuid.uuid4())[:8],
            description=description,
            worker_type=worker_type,
            depends_on=depends_on or [],
        )


class TaskGraph:
    """In-memory task graph with DB persistence."""

    def __init__(self, session_id: str, db_path: Path | None = None) -> None:
        self._session_id = session_id
        self._db_path = db_path
        self._nodes: dict[str, TaskNode] = {}

    # ------------------------------------------------------------------
    # Build / load
    # ------------------------------------------------------------------

    def add(self, node: TaskNode) -> None:
        self._nodes[node.id] = node
        store.upsert_task(
            self._session_id,
            task_id=node.id,
            description=node.description,
            worker_type=node.worker_type,
            depends_on=node.depends_on,
            status=node.status,
            db_path=self._db_path,
        )

    def load_from_db(self) -> None:
        rows = store.get_tasks(self._session_id, db_path=self._db_path)
        for row in rows:
            self._nodes[row["id"]] = TaskNode(
                id=row["id"],
                description=row["description"],
                worker_type=row["worker_type"],
                depends_on=row["depends_on"],
                status=row["status"],
                result=row["result"],
                output_files=row["output_files"],
                assigned_session=row["assigned_session"],
            )

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def mark_running(self, task_id: str, assigned_session: str = "") -> None:
        node = self._nodes[task_id]
        node.status = "running"
        node.assigned_session = assigned_session
        store.update_task_status(
            self._session_id, task_id, "running",
            assigned_session=assigned_session,
            db_path=self._db_path,
        )

    def mark_done(self, task_id: str, result: str, output_files: list[str] | None = None) -> None:
        node = self._nodes[task_id]
        node.status = "done"
        node.result = result
        node.output_files = output_files or []
        store.update_task_status(
            self._session_id, task_id, "done",
            result=result,
            output_files=output_files or [],
            db_path=self._db_path,
        )

    def mark_failed(self, task_id: str, result: str) -> None:
        node = self._nodes[task_id]
        node.status = "failed"
        node.result = result
        store.update_task_status(
            self._session_id, task_id, "failed",
            result=result,
            db_path=self._db_path,
        )

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def ready_tasks(self) -> list[TaskNode]:
        """Return tasks whose dependencies are all done and that are still pending."""
        done_ids = {n.id for n in self._nodes.values() if n.status == "done"}
        return [
            n for n in self._nodes.values()
            if n.status == "pending" and all(dep in done_ids for dep in n.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(n.status in ("done", "failed") for n in self._nodes.values())

    def has_failures(self) -> bool:
        return any(n.status == "failed" for n in self._nodes.values())

    def all_nodes(self) -> list[TaskNode]:
        return list(self._nodes.values())

    def summary(self) -> str:
        lines = []
        for node in self._nodes.values():
            icon = {"pending": "○", "running": "◌", "done": "✓", "failed": "✗"}.get(node.status, "?")
            lines.append(f"  {icon} [{node.worker_type}] {node.description}")
            if node.result:
                lines.append(f"      → {node.result[:120]}")
        return "\n".join(lines)
