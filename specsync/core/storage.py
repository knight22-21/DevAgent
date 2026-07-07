"""All path resolution using platformdirs.

This module is the single source of truth for all file paths in SpecSync.
It uses platformdirs to resolve correct data/config directories per OS.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import platformdirs


APP_NAME = "specsync"


def get_config_path() -> Path:
    """Return the path to the config file.

    On Windows: %APPDATA%\\specsync\\config.toml
    """
    config_dir = Path(platformdirs.user_config_dir(APP_NAME))
    return config_dir / "config.toml"


def get_data_dir() -> Path:
    """Return the base data directory.

    On Windows: %LOCALAPPDATA%\\specsync
    """
    return Path(platformdirs.user_data_dir(APP_NAME))


def get_project_hash(project_root: Path) -> str:
    """Compute a deterministic SHA256 hash of the absolute project path.

    This ensures the same project always maps to the same folder
    regardless of how SpecSync is invoked.
    """
    absolute = str(project_root.resolve())
    return hashlib.sha256(absolute.encode("utf-8")).hexdigest()


def get_project_dir(project_root: Path) -> Path:
    """Return the project-specific data directory.

    data_dir/projects/{project_hash}
    """
    return get_data_dir() / "projects" / get_project_hash(project_root)


def get_chroma_dir(project_root: Path) -> Path:
    """Return the ChromaDB directory for a project.

    project_dir/chroma
    """
    return get_project_dir(project_root) / "chroma"


def get_sqlite_path(project_root: Path) -> Path:
    """Return the SQLite database path for a project.

    project_dir/specsync.db
    """
    return get_project_dir(project_root) / "specsync.db"


def get_reports_dir(project_root: Path) -> Path:
    """Return the reports directory for a project.

    data_dir/reports/{project_hash}
    """
    return get_data_dir() / "reports" / get_project_hash(project_root)


def ensure_dirs(project_root: Path) -> None:
    """Create all required directories for a project if they don't exist."""
    dirs = [
        get_config_path().parent,
        get_project_dir(project_root),
        get_chroma_dir(project_root),
        get_reports_dir(project_root),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
