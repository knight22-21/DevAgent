"""Phase 16 — Vision, Notebook, and Todo tool tests."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IMAGE_SENTINEL = "\n__image__:"


def _make_registry():
    from devagent.tools.registry import ToolRegistry
    return ToolRegistry()


# ---------------------------------------------------------------------------
# 16.1 Vision tools — read_image
# ---------------------------------------------------------------------------

class TestReadImageTool:
    def test_read_image_missing_file(self, tmp_path: Path) -> None:
        from devagent.tools.vision_tools import register_vision_tools
        reg = _make_registry()
        register_vision_tools(reg, str(tmp_path), provider="anthropic")
        result = reg.call("read_image", {"path": "does_not_exist.png"})
        assert "[error]" in result
        assert "not found" in result.lower()

    def test_read_image_unsupported_extension(self, tmp_path: Path) -> None:
        from devagent.tools.vision_tools import register_vision_tools
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")
        reg = _make_registry()
        register_vision_tools(reg, str(tmp_path), provider="anthropic")
        result = reg.call("read_image", {"path": "doc.pdf"})
        assert "[error]" in result
        assert "Unsupported" in result

    def test_read_image_returns_sentinel_for_vision_provider(self, tmp_path: Path) -> None:
        from devagent.tools.vision_tools import register_vision_tools
        img = tmp_path / "test.png"
        # Minimal 1x1 PNG bytes
        img.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        reg = _make_registry()
        register_vision_tools(reg, str(tmp_path), provider="anthropic")
        result = reg.call("read_image", {"path": "test.png"})
        assert _IMAGE_SENTINEL in result
        assert "image/png" in result

    def test_read_image_strips_image_for_ollama(self, tmp_path: Path) -> None:
        from devagent.tools.vision_tools import register_vision_tools
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        reg = _make_registry()
        register_vision_tools(reg, str(tmp_path), provider="ollama")
        result = reg.call("read_image", {"path": "test.png"})
        assert _IMAGE_SENTINEL not in result
        assert "Vision not supported" in result

    def test_read_image_requires_path(self, tmp_path: Path) -> None:
        from devagent.tools.vision_tools import register_vision_tools
        reg = _make_registry()
        register_vision_tools(reg, str(tmp_path), provider="anthropic")
        result = reg.call("read_image", {})
        assert "[error]" in result


# ---------------------------------------------------------------------------
# 16.2 Image sentinel — _to_anthropic_messages
# ---------------------------------------------------------------------------

class TestAnthropicImageSentinel:
    def _make_tool_result_msg(self, content: str):
        from devagent.core.llm import AgentMessage
        return AgentMessage(
            role="tool_result",
            content=content,
            tool_call_id="tc123",
            tool_name="read_image",
        )

    def test_plain_tool_result_unchanged(self) -> None:
        from devagent.core.llm import _to_anthropic_messages
        msg = self._make_tool_result_msg("some text output")
        result = _to_anthropic_messages([msg])
        tr = result[0]["content"][0]
        assert tr["type"] == "tool_result"
        assert tr["content"] == "some text output"

    def test_image_sentinel_produces_content_list(self) -> None:
        from devagent.core.llm import _to_anthropic_messages
        b64 = base64.standard_b64encode(b"fake_image_data").decode()
        content = f"Image loaded: test.png{_IMAGE_SENTINEL}image/png:{b64}"
        msg = self._make_tool_result_msg(content)
        result = _to_anthropic_messages([msg])
        tr = result[0]["content"][0]
        assert tr["type"] == "tool_result"
        assert isinstance(tr["content"], list)
        types = [block["type"] for block in tr["content"]]
        assert "text" in types
        assert "image" in types

    def test_image_block_has_correct_media_type(self) -> None:
        from devagent.core.llm import _to_anthropic_messages
        b64 = base64.standard_b64encode(b"fake").decode()
        content = f"Loaded{_IMAGE_SENTINEL}image/jpeg:{b64}"
        msg = self._make_tool_result_msg(content)
        result = _to_anthropic_messages([msg])
        tr = result[0]["content"][0]
        image_block = next(b for b in tr["content"] if b["type"] == "image")
        assert image_block["source"]["media_type"] == "image/jpeg"
        assert image_block["source"]["type"] == "base64"
        assert image_block["source"]["data"] == b64


# ---------------------------------------------------------------------------
# 16.3 Image sentinel — _to_openai_messages strips sentinel
# ---------------------------------------------------------------------------

class TestOpenAIImageSentinel:
    def _make_tool_result_msg(self, content: str):
        from devagent.core.llm import AgentMessage
        return AgentMessage(
            role="tool_result",
            content=content,
            tool_call_id="tc456",
            tool_name="read_image",
        )

    def test_sentinel_stripped_from_openai_tool_result(self) -> None:
        from devagent.core.llm import _to_openai_messages
        b64 = base64.standard_b64encode(b"fake").decode()
        content = f"Image loaded{_IMAGE_SENTINEL}image/png:{b64}"
        msg = self._make_tool_result_msg(content)
        result = _to_openai_messages([msg])
        assert result[0]["content"] == "Image loaded"
        assert _IMAGE_SENTINEL not in result[0]["content"]

    def test_plain_tool_result_unchanged_openai(self) -> None:
        from devagent.core.llm import _to_openai_messages
        msg = self._make_tool_result_msg("plain output")
        result = _to_openai_messages([msg])
        assert result[0]["content"] == "plain output"


# ---------------------------------------------------------------------------
# 16.4 Notebook tools
# ---------------------------------------------------------------------------

class TestNotebookTools:
    def _make_notebook(self, cells: list[dict]) -> dict:
        """Minimal valid nbformat v4 notebook dict."""
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
            "cells": cells,
        }

    def test_notebook_read_missing_file(self, tmp_path: Path) -> None:
        try:
            import nbformat  # noqa: F401
        except ImportError:
            return  # skip if not installed

        from devagent.tools.notebook_tools import register_notebook_tools
        reg = _make_registry()
        register_notebook_tools(reg, str(tmp_path))
        result = reg.call("notebook_read", {"path": "missing.ipynb"})
        assert "[error]" in result

    def test_notebook_read_returns_cells(self, tmp_path: Path) -> None:
        try:
            import nbformat
        except ImportError:
            return

        nb = nbformat.v4.new_notebook()
        nb.cells = [
            nbformat.v4.new_code_cell("x = 1 + 1"),
            nbformat.v4.new_markdown_cell("## Title"),
        ]
        nb_path = tmp_path / "test.ipynb"
        nbformat.write(nb, str(nb_path))

        from devagent.tools.notebook_tools import register_notebook_tools
        reg = _make_registry()
        register_notebook_tools(reg, str(tmp_path))
        result = reg.call("notebook_read", {"path": "test.ipynb"})
        assert "x = 1 + 1" in result
        assert "## Title" in result

    def test_notebook_edit_updates_cell(self, tmp_path: Path) -> None:
        try:
            import nbformat
        except ImportError:
            return

        nb = nbformat.v4.new_notebook()
        nb.cells = [nbformat.v4.new_code_cell("old_code()")]
        nb_path = tmp_path / "edit_test.ipynb"
        nbformat.write(nb, str(nb_path))

        from devagent.tools.notebook_tools import register_notebook_tools
        reg = _make_registry()
        register_notebook_tools(reg, str(tmp_path))
        result = reg.call("notebook_edit", {
            "path": "edit_test.ipynb", "cell_index": 0, "source": "new_code()"
        })
        assert "updated" in result.lower()
        nb_after = nbformat.read(str(nb_path), as_version=4)
        assert nb_after.cells[0].source == "new_code()"

    def test_notebook_edit_missing_file(self, tmp_path: Path) -> None:
        try:
            import nbformat  # noqa: F401
        except ImportError:
            return

        from devagent.tools.notebook_tools import register_notebook_tools
        reg = _make_registry()
        register_notebook_tools(reg, str(tmp_path))
        result = reg.call("notebook_edit", {
            "path": "ghost.ipynb", "cell_index": 0, "source": "x=1"
        })
        assert "[error]" in result

    def test_notebook_run_missing_jupyter(self, tmp_path: Path) -> None:
        try:
            import nbformat
        except ImportError:
            return

        nb = nbformat.v4.new_notebook()
        nb.cells = [nbformat.v4.new_code_cell("print('hello')")]
        nb_path = tmp_path / "run_test.ipynb"
        nbformat.write(nb, str(nb_path))

        from devagent.tools.notebook_tools import register_notebook_tools
        reg = _make_registry()
        register_notebook_tools(reg, str(tmp_path))

        with patch("subprocess.run", side_effect=FileNotFoundError("jupyter")):
            result = reg.call("notebook_run", {"path": "run_test.ipynb"})
        assert "jupyter not found" in result


# ---------------------------------------------------------------------------
# 16.5 Todo tools
# ---------------------------------------------------------------------------

class TestTodoTools:
    def test_todo_write_and_read(self, tmp_path: Path) -> None:
        from devagent.tools.todo_tools import register_todo_tools
        reg = _make_registry()
        session_id = "test-session-16"

        with patch("devagent.session.store.upsert_memory") as mock_upsert, \
             patch("devagent.session.store.get_memory") as mock_get:
            mock_get.return_value = {
                "__todos__": [
                    {"title": "Write tests", "status": "done"},
                    {"title": "Open PR", "status": "pending"},
                ]
            }
            register_todo_tools(reg, session_id)

            write_result = reg.call("todo_write", {
                "tasks": [
                    {"title": "Write tests", "status": "done"},
                    {"title": "Open PR", "status": "pending"},
                ]
            })
            assert "2 todo" in write_result
            mock_upsert.assert_called_once()

            read_result = reg.call("todo_read", {})
            assert "Write tests" in read_result
            assert "[x]" in read_result
            assert "[ ]" in read_result
            assert "Open PR" in read_result

    def test_todo_write_string_tasks(self, tmp_path: Path) -> None:
        from devagent.tools.todo_tools import register_todo_tools
        reg = _make_registry()
        with patch("devagent.session.store.upsert_memory") as mock_upsert:
            register_todo_tools(reg, "sess-42")
            result = reg.call("todo_write", {"tasks": ["task A", "task B"]})
            assert "2 todo" in result
            saved_tasks = mock_upsert.call_args[0][2]
            assert saved_tasks[0]["title"] == "task A"
            assert saved_tasks[0]["status"] == "pending"

    def test_todo_read_empty(self) -> None:
        from devagent.tools.todo_tools import register_todo_tools
        reg = _make_registry()
        with patch("devagent.session.store.get_memory", return_value={}):
            register_todo_tools(reg, "sess-empty")
            result = reg.call("todo_read", {})
            assert "No todos" in result

    def test_todo_write_invalid_status(self) -> None:
        from devagent.tools.todo_tools import register_todo_tools
        reg = _make_registry()
        with patch("devagent.session.store.upsert_memory"):
            register_todo_tools(reg, "sess-err")
            result = reg.call("todo_write", {
                "tasks": [{"title": "bad task", "status": "invalid"}]
            })
            assert "[error]" in result

    def test_todo_in_progress_icon(self) -> None:
        from devagent.tools.todo_tools import register_todo_tools
        reg = _make_registry()
        with patch("devagent.session.store.get_memory") as mock_get:
            mock_get.return_value = {
                "__todos__": [{"title": "Working on it", "status": "in_progress"}]
            }
            register_todo_tools(reg, "sess-wip")
            result = reg.call("todo_read", {})
            assert "[~]" in result
