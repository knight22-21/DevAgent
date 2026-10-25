from __future__ import annotations

import time
from pathlib import Path

from devagent.codeprism.watcher import ProjectIndexWatcher


def test_watcher_syncs_stable_changed_file(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("value = 1", encoding="utf-8")
    updates: list[str] = []
    watcher = ProjectIndexWatcher(tmp_path, updates.append, debounce=0)

    source.write_text("value = 2", encoding="utf-8")
    assert watcher.scan_once() == [source]
    assert updates == [str(source)]


def test_watcher_syncs_deleted_file(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("value = 1", encoding="utf-8")
    updates: list[str] = []
    watcher = ProjectIndexWatcher(tmp_path, updates.append, debounce=0)

    source.unlink()
    assert watcher.scan_once() == [source]
    assert updates == [str(source)]


def test_watcher_ignores_build_directories(tmp_path: Path) -> None:
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    source = ignored / "module.js"
    source.write_text("const value = 1", encoding="utf-8")
    updates: list[str] = []
    watcher = ProjectIndexWatcher(tmp_path, updates.append, debounce=0)

    source.write_text("const value = 2", encoding="utf-8")
    assert watcher.scan_once() == []
    assert updates == []


def test_watcher_debounces_changes(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("value = 1", encoding="utf-8")
    updates: list[str] = []
    watcher = ProjectIndexWatcher(tmp_path, updates.append, debounce=0.05)

    source.write_text("value = 2", encoding="utf-8")
    assert watcher.scan_once() == []
    time.sleep(0.06)
    assert watcher.scan_once() == [source]
