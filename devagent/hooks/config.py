"""Hook definition models and loader for DevAgent hooks system."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

HookType = Literal["command", "http", "prompt"]
HookEvent = Literal["pre_tool_use", "post_tool_use", "session_start", "session_end", "file_write"]


@dataclass
class HookDef:
    event: str
    type: str
    command: str = ""
    url: str = ""
    prompt: str = ""      # LLM evaluator prompt template (prompt hook type)
    tool: str = ""        # empty = match all tools

    def matches(self, event: str, tool_name: str) -> bool:
        """Return True if this hook should fire for the given event + tool."""
        # file_write is an alias: fires on pre_tool_use for write_file / edit_file
        if self.event == "file_write":
            if event != "pre_tool_use":
                return False
            return tool_name in ("write_file", "edit_file")
        if self.event != event:
            return False
        return not self.tool or self.tool == tool_name


def load_hooks(project_root: str | Path) -> list[HookDef]:
    """Load hook definitions from .devagent/hooks.toml in project_root (returns [] if absent)."""
    path = Path(project_root) / ".devagent" / "hooks.toml"
    if not path.is_file():
        return []
    with open(path, "rb") as f:
        data = tomllib.load(f)
    hooks: list[HookDef] = []
    for entry in data.get("hooks", []):
        hooks.append(HookDef(
            event=entry.get("event", "pre_tool_use"),
            type=entry.get("type", "command"),
            command=entry.get("command", ""),
            url=entry.get("url", ""),
            prompt=entry.get("prompt", ""),
            tool=entry.get("tool", ""),
        ))
    return hooks
