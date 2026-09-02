"""File-based cross-session project memory.

Facts are stored in <project_root>/.devagent/memory.md as a Markdown list
so they persist across sessions and can be inspected or edited by hand:

  # DevAgent Memory
  <!-- auto-managed — edit with care -->
  - framework: FastAPI
  - test_command: pytest tests/ -q
  - auth_module: devagent/core/auth.py

On session start, these facts are merged into the SQLite MemoryBlock.
When the agent calls remember_fact / forget_fact, the file is kept in sync.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_MEMORY_FILE = ".devagent/memory.md"
_HEADER = "# DevAgent Memory\n<!-- auto-managed — edit with care -->\n"
_ITEM_RE = re.compile(r"^-\s+(\S+?):\s+(.+)$", re.MULTILINE)


class ProjectMemory:
    """Read/write .devagent/memory.md for cross-session fact persistence."""

    def __init__(self, project_root: str | Path) -> None:
        self._path = Path(project_root) / _MEMORY_FILE

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, str]:
        """Parse memory.md and return a key → value dict. Returns {} if missing."""
        if not self._path.exists():
            return {}
        text = self._path.read_text(encoding="utf-8")
        return {m.group(1): m.group(2).strip() for m in _ITEM_RE.finditer(text)}

    def save(self, facts: dict[str, Any]) -> None:
        """Overwrite memory.md with all facts, sorted by key."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [_HEADER]
        for key in sorted(facts):
            lines.append(f"- {key}: {facts[key]}")
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def upsert(self, key: str, value: Any) -> None:
        facts = self.load()
        facts[key] = str(value)
        self.save(facts)

    def delete(self, key: str) -> None:
        facts = self.load()
        if key not in facts:
            return
        facts.pop(key)
        if facts:
            self.save(facts)
        else:
            self._path.write_text(_HEADER + "\n", encoding="utf-8")
