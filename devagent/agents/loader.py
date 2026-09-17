"""Agent definition file loader — reads .devagent/agents/*.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentDef:
    name: str
    description: str = ""
    worker_type: str = "implementer"
    model: str = "coding"
    max_iter: int = 30
    tools: list = field(default_factory=list)
    permission: str = "default"
    memory: str = "session"       # "session" | "project"
    prompt: str = ""
    isolation: str = ""           # "worktree" | ""


def load_agent_defs(project_root: str | Path) -> dict[str, AgentDef]:
    """Load agent definitions from .devagent/agents/*.toml and user config dir.

    Project-level definitions override user-level ones with the same name.
    Returns a dict keyed by agent name.
    """
    try:
        import platformdirs
        user_agents_dir = Path(platformdirs.user_config_dir("devagent")) / "agents"
    except ImportError:
        user_agents_dir = None

    search_dirs: list[Path] = []
    if user_agents_dir:
        search_dirs.append(user_agents_dir)
    search_dirs.append(Path(project_root) / ".devagent" / "agents")

    defs: dict[str, AgentDef] = {}
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for toml_path in sorted(search_dir.glob("*.toml")):
            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
                name = data.get("name", toml_path.stem)
                defs[name] = AgentDef(
                    name=name,
                    description=data.get("description", ""),
                    worker_type=data.get("worker_type", "implementer"),
                    model=data.get("model", "coding"),
                    max_iter=int(data.get("max_iter", 30)),
                    tools=list(data.get("tools", [])),
                    permission=data.get("permission", "default"),
                    memory=data.get("memory", "session"),
                    prompt=data.get("prompt", ""),
                    isolation=data.get("isolation", ""),
                )
            except Exception:
                pass  # skip malformed files silently

    return defs
