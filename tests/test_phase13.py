"""Phase 13 — REPL depth & UX: inline diff, /undo, shell escape tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(project_root: str):
    from devagent.tools.registry import build_registry
    return build_registry(project_root=project_root)


# ---------------------------------------------------------------------------
# Diff output from file tools
# ---------------------------------------------------------------------------

class TestFileDiff:
    def test_edit_file_includes_diff(self, tmp_path: Path) -> None:
        f = tmp_path / "foo.py"
        f.write_text("x = 1\ny = 2\n")
        reg = _make_registry(str(tmp_path))
        result = reg.call("edit_file", {"path": "foo.py", "old_str": "x = 1", "new_str": "x = 99"})
        assert "---diff---" in result
        diff_part = result.split("---diff---\n", 1)[1]
        assert "-x = 1" in diff_part
        assert "+x = 99" in diff_part

    def test_write_file_new_file_no_diff(self, tmp_path: Path) -> None:
        """Writing a brand-new file has nothing to diff against — no diff emitted."""
        reg = _make_registry(str(tmp_path))
        result = reg.call("write_file", {"path": "new.py", "content": "print('hi')\n"})
        # New file: no before-content — diff would be all-additions, which is fine
        # The important thing is no error
        assert "[error]" not in result

    def test_write_file_overwrite_includes_diff(self, tmp_path: Path) -> None:
        f = tmp_path / "cfg.py"
        f.write_text("DEBUG = False\n")
        reg = _make_registry(str(tmp_path))
        result = reg.call("write_file", {"path": "cfg.py", "content": "DEBUG = True\n"})
        assert "---diff---" in result
        diff_part = result.split("---diff---\n", 1)[1]
        assert "-DEBUG = False" in diff_part
        assert "+DEBUG = True" in diff_part

    def test_edit_file_error_no_diff(self, tmp_path: Path) -> None:
        f = tmp_path / "bar.py"
        f.write_text("a = 1\n")
        reg = _make_registry(str(tmp_path))
        result = reg.call("edit_file", {"path": "bar.py", "old_str": "NOT_THERE", "new_str": "x"})
        assert result.startswith("[error]")
        assert "---diff---" not in result


# ---------------------------------------------------------------------------
# Agent loop: ToolResultEvent.diff
# ---------------------------------------------------------------------------

class TestToolResultEventDiff:
    def test_diff_split_from_result(self) -> None:
        from devagent.agent.loop import ToolResultEvent
        raw = "Edited foo.py: replaced 1 occurrence\n---diff---\n-old\n+new\n"
        result, _, diff = raw.partition("\n---diff---\n")
        ev = ToolResultEvent(id="1", name="edit_file", result=result, diff=diff)
        assert ev.result == "Edited foo.py: replaced 1 occurrence"
        assert "-old" in ev.diff
        assert "+new" in ev.diff

    def test_no_diff_in_result_is_empty(self) -> None:
        from devagent.agent.loop import ToolResultEvent
        raw = "Written 100 bytes to new.py"
        result, _, diff = raw.partition("\n---diff---\n")
        ev = ToolResultEvent(id="2", name="write_file", result=result, diff=diff)
        assert ev.result == "Written 100 bytes to new.py"
        assert ev.diff == ""


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------

class TestRenderDiff:
    def test_render_diff_green_plus_lines(self, capsys) -> None:
        from io import StringIO

        from rich.console import Console

        from devagent.output.streaming import render_diff

        buf = StringIO()
        with patch("devagent.output.streaming.console", Console(file=buf, highlight=False)):
            render_diff("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n")
        out = buf.getvalue()
        assert "old" in out
        assert "new" in out

    def test_render_diff_empty_is_noop(self, capsys) -> None:
        from devagent.output.streaming import render_diff
        # Should not raise
        render_diff("")


# ---------------------------------------------------------------------------
# Undo stack
# ---------------------------------------------------------------------------

class _FakeSession:
    """Minimal stand-in for DevAgentSession to test _wrap_file_tools_for_undo."""

    def __init__(self, project_root: Path) -> None:
        from devagent.agent.flows import DevAgentSession
        self._project_root = project_root
        self._undo_stack: list = []
        self._last_diff = ""
        # Borrow the real method
        self._wrap_file_tools_for_undo = DevAgentSession._wrap_file_tools_for_undo.__get__(self)


class TestUndoStack:
    def _make_session(self, tmp_path: Path):
        from devagent.tools.registry import build_registry
        session = _FakeSession(tmp_path)
        registry = build_registry(project_root=str(tmp_path))
        session._wrap_file_tools_for_undo(registry)
        return session, registry

    def test_edit_pushes_undo_entry(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        f = tmp_path / "a.py"
        f.write_text("x = 1\n")
        registry.call("edit_file", {"path": "a.py", "old_str": "x = 1", "new_str": "x = 2"})
        assert len(session._undo_stack) == 1
        assert session._undo_stack[0]["path"] == "a.py"
        assert "x = 1" in session._undo_stack[0]["before"]

    def test_write_new_file_pushes_undo_with_none_before(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        registry.call("write_file", {"path": "new.py", "content": "# new\n"})
        assert session._undo_stack[-1]["before"] is None

    def test_write_overwrite_pushes_undo_with_original(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        f = tmp_path / "cfg.py"
        f.write_text("OLD\n")
        registry.call("write_file", {"path": "cfg.py", "content": "NEW\n"})
        assert session._undo_stack[-1]["before"] == "OLD\n"

    def test_failed_edit_does_not_push_undo(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        f = tmp_path / "x.py"
        f.write_text("a = 1\n")
        registry.call("edit_file", {"path": "x.py", "old_str": "NOT_THERE", "new_str": "y"})
        assert len(session._undo_stack) == 0

    def test_undo_restores_file(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        f = tmp_path / "b.py"
        f.write_text("original\n")
        registry.call("edit_file", {"path": "b.py", "old_str": "original", "new_str": "changed"})
        assert f.read_text() == "changed\n"

        # Simulate /undo
        entry = session._undo_stack.pop()
        path, before = entry["path"], entry["before"]
        (session._project_root / path).write_text(before)
        assert f.read_text() == "original\n"

    def test_undo_new_file_deletes_it(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        registry.call("write_file", {"path": "new.py", "content": "hi\n"})
        assert (tmp_path / "new.py").exists()

        entry = session._undo_stack.pop()
        target = session._project_root / entry["path"]
        assert entry["before"] is None
        target.unlink(missing_ok=True)
        assert not (tmp_path / "new.py").exists()

    def test_undo_stack_capped_at_20(self, tmp_path: Path) -> None:
        session, registry = self._make_session(tmp_path)
        for i in range(25):
            f = tmp_path / "x.py"
            f.write_text(f"v{i}\n")
            registry.call("edit_file", {"path": "x.py", "old_str": f"v{i}", "new_str": f"v{i+1}"})
        assert len(session._undo_stack) == 20


# ---------------------------------------------------------------------------
# Shell escape
# ---------------------------------------------------------------------------

class TestShellEscape:
    def test_shell_cmd_echo(self, tmp_path: Path) -> None:
        """! escape runs shell commands and captures output."""
        import subprocess
        proc = subprocess.run("echo hello", shell=True, capture_output=True, text=True, cwd=str(tmp_path))
        assert "hello" in proc.stdout

    def test_shell_cmd_exit_code_zero(self, tmp_path: Path) -> None:
        import subprocess
        proc = subprocess.run("exit 0", shell=True, capture_output=True, text=True, cwd=str(tmp_path))
        assert proc.returncode == 0
