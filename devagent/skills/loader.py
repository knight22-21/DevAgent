"""Skills loader — built-in + user-defined skills from ~/.config/devagent/skills/*.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    name: str                             # slash command name, e.g. "explain"
    description: str
    prompt: str                           # injected task/system text when skill runs
    tools_only: list[str] = field(default_factory=list)  # empty = all tools
    model: str = ""                       # "" = session default; "cheap"/"reviewing" = router tier
    max_iter: int = 0                     # 0 = use session default
    user_invocable: bool = True


def load_all_skills() -> dict[str, Skill]:
    """Return all skills: built-ins + user-defined TOML files.

    Built-in skills are defined in devagent/skills/builtin.py.
    User skills live in ~/.config/devagent/skills/*.toml.
    User skills with the same name as a built-in override the built-in.
    """
    skills: dict[str, Skill] = {}

    # Load built-ins first
    try:
        from devagent.skills.builtin import BUILTIN_SKILLS
        for s in BUILTIN_SKILLS:
            skills[s.name] = s
    except Exception:
        pass

    # Load user-defined skills
    user_dir = Path.home() / ".config" / "devagent" / "skills"
    if user_dir.exists():
        for toml_file in sorted(user_dir.glob("*.toml")):
            try:
                with open(toml_file, "rb") as f:
                    data = tomllib.load(f)
                skill = Skill(
                    name=str(data["name"]),
                    description=str(data.get("description", "")),
                    prompt=str(data.get("prompt", "")),
                    tools_only=list(data.get("tools_only", [])),
                    model=str(data.get("model", "")),
                    max_iter=int(data.get("max_iter", 0)),
                    user_invocable=bool(data.get("user_invocable", True)),
                )
                skills[skill.name] = skill
            except Exception:
                pass  # skip malformed TOML files silently

    return skills
