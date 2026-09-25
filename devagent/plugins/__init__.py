"""DevAgent plugin bundle system.

Third-party packages declare themselves via the ``devagent.plugins`` entry-point
group in their ``pyproject.toml``::

    [project.entry-points."devagent.plugins"]
    my-plugin = "my_package.plugin:bundle"

The entry-point value must be either a :class:`PluginBundle` instance or a
zero-argument callable that returns one.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import entry_points


@dataclass
class PluginBundle:
    """Metadata and extensions contributed by a plugin package."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    # Each list entry is a plain dict so plugins don't need to import devagent
    # internals — devagent can convert them lazily when needed.
    skills: list[dict] = field(default_factory=list)
    hooks: list[dict] = field(default_factory=list)
    mcp_servers: list[dict] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


def load_plugins() -> list[PluginBundle]:
    """Discover and return all installed plugin bundles.

    Uses ``importlib.metadata`` entry points under the ``devagent.plugins``
    group.  Malformed or crashing plugins are silently skipped.
    """
    bundles: list[PluginBundle] = []
    eps = entry_points(group="devagent.plugins")
    for ep in eps:
        try:
            obj = ep.load()
            if callable(obj) and not isinstance(obj, PluginBundle):
                obj = obj()
            if isinstance(obj, PluginBundle):
                bundles.append(obj)
        except Exception:
            pass
    return bundles


def install_plugin(package: str) -> tuple[bool, str]:
    """Install a plugin package with pip.

    Returns ``(success, output)`` where *output* is combined stdout/stderr.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output
