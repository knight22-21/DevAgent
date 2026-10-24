"""find_files must not admit a sibling whose name starts with the root's."""

from __future__ import annotations

from devagent.tools.registry import ToolRegistry
from devagent.tools.search_tools import register_search_tools


def _registry(project_root) -> ToolRegistry:
    registry = ToolRegistry()
    register_search_tools(registry, str(project_root))
    return registry


def test_find_files_rejects_a_sibling_sharing_the_name_prefix(tmp_path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    sibling = tmp_path / "proj-private"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("nope", encoding="utf-8")

    result = _registry(project).call("find_files", {"path": "../proj-private", "pattern": "*.txt"})

    assert result == "[error] path escapes project root"
    assert "secret.txt" not in result


def test_find_files_still_lists_files_inside_the_project(tmp_path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "notes.txt").write_text("hello", encoding="utf-8")

    result = _registry(project).call("find_files", {"pattern": "*.txt"})

    assert result == "notes.txt"


def test_find_files_rejects_plain_traversal(tmp_path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (tmp_path / "outside.txt").write_text("nope", encoding="utf-8")

    result = _registry(project).call("find_files", {"path": "..", "pattern": "*.txt"})

    assert result == "[error] path escapes project root"
