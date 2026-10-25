"""Debounced project file watcher for automatic CodePrism synchronization."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

_WATCHED_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".json", ".kt", ".kts", ".md", ".php", ".py", ".rb", ".rs", ".sh", ".sql",
    ".swift", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
}
_IGNORED_DIRECTORIES = {
    ".git", ".codeprism", ".devagent", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".venv", "__pycache__", "node_modules", "venv",
}


class ProjectIndexWatcher:
    """Poll for stable file changes and update CodePrism incrementally."""

    def __init__(
        self,
        project_root: Path,
        update_file: Callable[[str], object],
        *,
        interval: float = 1.0,
        debounce: float = 1.0,
    ) -> None:
        self.project_root = project_root.resolve()
        self._update_file = update_file
        self._interval = interval
        self._debounce = debounce
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = self._take_snapshot()
        self._pending: dict[Path, tuple[tuple[int, int], float]] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="devagent-codeprism-watcher",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(self._interval * 2, 1.0))

    def scan_once(self) -> list[Path]:
        """Process stable changes once; exposed for deterministic tests."""
        now = time.monotonic()
        current = self._take_snapshot()
        changed = {
            path for path in set(self._snapshot) | set(current)
            if self._snapshot.get(path) != current.get(path)
        }
        self._snapshot = current

        for path in changed:
            signature = current.get(path, (0, 0))
            self._pending[path] = (signature, now)

        synced: list[Path] = []
        for path, (signature, changed_at) in list(self._pending.items()):
            if current.get(path, (0, 0)) != signature:
                continue
            if now - changed_at < self._debounce:
                continue
            self._update_file(str(path))
            synced.append(path)
            del self._pending[path]
        return synced

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self.scan_once()
            except OSError:
                # A file can disappear between directory scan and stat.
                continue

    def _take_snapshot(self) -> dict[Path, tuple[int, int]]:
        snapshot: dict[Path, tuple[int, int]] = {}
        for path in self.project_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _WATCHED_SUFFIXES:
                continue
            if any(part in _IGNORED_DIRECTORIES for part in path.relative_to(self.project_root).parts):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[path] = (stat.st_mtime_ns, stat.st_size)
        return snapshot
