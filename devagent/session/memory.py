"""Structured session memory -- inject remembered facts into the system prompt.

Memory items are stored in the DB via store.upsert_memory and loaded here
so the agent always has relevant context without bloating the main conversation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from devagent.session import store

_SYSTEM_BLOCK_HEADER = "\n\n## Session Memory\n"
_ITEM_PREFIX = "- "


class MemoryBlock:
    """In-memory cache of structured facts that gets injected into the system prompt.

    When project_memory is provided (Phase 12), facts are also persisted to
    .devagent/memory.md so they survive across sessions.
    """

    def __init__(
        self,
        session_id: str,
        db_path: Path | None = None,
        project_memory=None,   # ProjectMemory | None
    ) -> None:
        self.session_id = session_id
        self.db_path = db_path
        self._project_memory = project_memory
        self._cache: dict[str, Any] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._cache = store.get_memory(
                self.session_id, scope="session", db_path=self.db_path
            )
            # Merge project-level facts (file wins for keys not already in SQLite)
            if self._project_memory is not None:
                for key, value in self._project_memory.load().items():
                    if key not in self._cache:
                        store.upsert_memory(
                            self.session_id, key, value,
                            scope="session", db_path=self.db_path
                        )
                        self._cache[key] = value
            self._loaded = True

    def set(self, key: str, value: Any, item_type: str = "fact") -> None:
        store.upsert_memory(
            self.session_id, key, value,
            scope="session", item_type=item_type, db_path=self.db_path
        )
        self._cache[key] = value
        if self._project_memory is not None:
            self._project_memory.upsert(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        self._ensure_loaded()
        return self._cache.get(key, default)

    def delete(self, key: str) -> None:
        store.delete_memory_key(
            self.session_id, key, scope="session", db_path=self.db_path
        )
        self._cache.pop(key, None)
        if self._project_memory is not None:
            self._project_memory.delete(key)

    def all(self) -> dict[str, Any]:
        self._ensure_loaded()
        return dict(self._cache)

    def as_prompt_block(self) -> str:
        """Return a formatted string to append to the system prompt.

        Returns empty string if there are no memory items.
        """
        self._ensure_loaded()
        if not self._cache:
            return ""
        lines = [_SYSTEM_BLOCK_HEADER]
        for key, value in sorted(self._cache.items()):
            if isinstance(value, (dict, list)):
                import json
                lines.append(f"{_ITEM_PREFIX}**{key}**: {json.dumps(value)}")
            else:
                lines.append(f"{_ITEM_PREFIX}**{key}**: {value}")
        return "\n".join(lines)
