"""Phase 16 — Todo tools backed by session memory store.

Todo items are persisted in memory_items under key "__todos__" with
item_type="todo" and scope="session".

Each task: {"title": str, "status": "pending" | "in_progress" | "done"}
"""

from __future__ import annotations

from typing import Any

_TODO_KEY = "__todos__"
_VALID_STATUSES = frozenset({"pending", "in_progress", "done"})
_STATUS_ICON: dict[str, str] = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "done": "[x]",
}


def register_todo_tools(registry, session_id: str) -> None:
    """Register todo_write and todo_read tools."""
    from devagent.session import store

    def todo_write(args: dict[str, Any]) -> str:
        tasks_raw = args.get("tasks", [])
        if not isinstance(tasks_raw, list):
            return "[error] tasks must be a JSON array"
        tasks: list[dict[str, str]] = []
        for item in tasks_raw:
            if isinstance(item, str):
                tasks.append({"title": item.strip(), "status": "pending"})
            elif isinstance(item, dict):
                title = str(item.get("title", "")).strip()
                status = item.get("status", "pending")
                if status not in _VALID_STATUSES:
                    return (
                        f"[error] Invalid status {status!r}. "
                        f"Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
                    )
                tasks.append({"title": title, "status": status})
            else:
                return f"[error] Each task must be a string or object, got: {type(item).__name__}"
        store.upsert_memory(session_id, _TODO_KEY, tasks, scope="session", item_type="todo")
        return f"Saved {len(tasks)} todo(s)"

    registry.register(
        "todo_write",
        (
            "Write or replace the todo list for this session. "
            "Each task is a string or an object with 'title' and optional "
            "'status' (pending|in_progress|done). Replaces the entire list."
        ),
        {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "List of task strings or objects",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "done"],
                                    },
                                },
                                "required": ["title"],
                            },
                        ]
                    },
                }
            },
            "required": ["tasks"],
        },
        todo_write,
    )

    def todo_read(args: dict[str, Any]) -> str:
        items = store.get_memory(session_id, scope="session")
        tasks = items.get(_TODO_KEY, [])
        if not tasks:
            return "No todos found."
        lines = [f"Todo list ({len(tasks)} item(s)):"]
        for i, task in enumerate(tasks):
            title = task.get("title", "")
            status = task.get("status", "pending")
            icon = _STATUS_ICON.get(status, "[ ]")
            lines.append(f"  {i + 1}. {icon} {title}")
        return "\n".join(lines)

    registry.register(
        "todo_read",
        "Read the current todo list for this session.",
        {"type": "object", "properties": {}},
        todo_read,
    )
