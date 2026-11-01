"""Notebook tools must keep their paths inside the project root."""

from __future__ import annotations

import pytest

pytest.importorskip("nbformat")

from devagent.tools.notebook_tools import register_notebook_tools
from devagent.tools.registry import ToolRegistry


def _registry(project_root) -> ToolRegistry:
    registry = ToolRegistry()
    register_notebook_tools(registry, str(project_root))
    return registry


def _write_notebook(path) -> None:
    import json

    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "id": "cell-1",
                "metadata": {},
                "outputs": [],
                "source": "print('hi')",
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook), encoding="utf-8")


@pytest.mark.parametrize("tool", ["notebook_read", "notebook_edit", "notebook_run"])
def test_traversal_is_rejected_before_the_file_is_touched(tmp_path, tool) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "evil.ipynb"
    _write_notebook(outside)

    args = {"path": "../evil.ipynb"}
    if tool == "notebook_edit":
        args.update(cell_index=0, source="print('pwned')")

    result = _registry(project).call(tool, args)

    assert result == "[error] path escapes project root", result


def test_absolute_paths_outside_the_project_are_rejected(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "evil.ipynb"
    _write_notebook(outside)

    result = _registry(project).call("notebook_read", {"path": str(outside)})

    assert result == "[error] path escapes project root", result


def test_notebook_inside_the_project_still_reads(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_notebook(project / "analysis.ipynb")

    result = _registry(project).call("notebook_read", {"path": "analysis.ipynb"})

    assert result.startswith("Notebook: analysis.ipynb"), result
