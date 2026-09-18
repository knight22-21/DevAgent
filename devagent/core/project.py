"""Project detection and project hash computation."""

from __future__ import annotations

from pathlib import Path

# Markers that indicate a project root directory
PROJECT_MARKERS = [".git", "pyproject.toml", "setup.py", "package.json"]


def detect_project_root(start_dir: Path | None = None) -> tuple[Path, bool]:
    """Walk up from start_dir looking for a project root marker.

    Returns a tuple of (project_root, found_marker).
    If no marker is found, returns (start_dir, False).
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    while True:
        for marker in PROJECT_MARKERS:
            if (current / marker).exists():
                return current, True

        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding a marker
            break
        current = parent

    return start_dir.resolve(), False
