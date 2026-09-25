"""Phase 21 — HTTP + prompt hook types and hooks test CLI improvements."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_hooks_toml(project: Path, content: str) -> None:
    devagent = project / ".devagent"
    devagent.mkdir(parents=True, exist_ok=True)
    (devagent / "hooks.toml").write_text(content)


# ---------------------------------------------------------------------------
# HookDef config — prompt field
# ---------------------------------------------------------------------------

class TestHookDefPromptField:
    def test_prompt_field_default_is_empty(self) -> None:
        from devagent.hooks.config import HookDef
        h = HookDef(event="pre_tool_use", type="prompt")
        assert h.prompt == ""

    def test_prompt_field_set(self) -> None:
        from devagent.hooks.config import HookDef
        h = HookDef(event="pre_tool_use", type="prompt", prompt="Is this safe? {tool_input}")
        assert "tool_input" in h.prompt

    def test_load_hooks_reads_prompt_field(self, tmp_path: Path) -> None:
        from devagent.hooks.config import load_hooks
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "prompt"
prompt = "Evaluate: {tool_input}"
tool = "run_shell"
""")
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].type == "prompt"
        assert "tool_input" in hooks[0].prompt


# ---------------------------------------------------------------------------
# HookRunner — prompt hook type
# ---------------------------------------------------------------------------

class TestPromptHook:
    def test_prompt_hook_allows_by_default_when_no_cfg(self, tmp_path: Path) -> None:
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "prompt"
prompt = "Evaluate: {tool_input}"
tool = "run_shell"
""")
        # No cfg passed — _cfg is None; patch load_config to fail so it stays None
        runner = HookRunner(tmp_path)
        with patch("devagent.core.config.load_config", side_effect=RuntimeError("no config")):
            result = runner.pre_tool_use("run_shell", {"command": "ls"})
        assert result.allowed  # fail-open

    def test_prompt_hook_allows_when_llm_returns_ok_true(self, tmp_path: Path) -> None:
        from devagent.core.llm import LLMResponse
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "prompt"
prompt = "Is this safe? {tool_input}"
tool = "run_shell"
""")
        mock_cfg = MagicMock()
        runner = HookRunner(tmp_path, cfg=mock_cfg)

        mock_resp = LLMResponse(content='{"ok": true, "reason": "looks fine"}')
        with patch("devagent.core.llm.LLMClient") as MockLLM:
            MockLLM.return_value.complete.return_value = mock_resp
            result = runner.pre_tool_use("run_shell", {"command": "ls"})
        assert result.allowed

    def test_prompt_hook_blocks_when_llm_returns_ok_false(self, tmp_path: Path) -> None:
        from devagent.core.llm import LLMResponse
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "prompt"
prompt = "Is this safe? {tool_input}"
tool = "run_shell"
""")
        mock_cfg = MagicMock()
        runner = HookRunner(tmp_path, cfg=mock_cfg)

        mock_resp = LLMResponse(content='{"ok": false, "reason": "rm -rf is dangerous"}')
        with patch("devagent.core.llm.LLMClient") as MockLLM:
            MockLLM.return_value.complete.return_value = mock_resp
            result = runner.pre_tool_use("run_shell", {"command": "rm -rf /"})
        assert not result.allowed
        assert "dangerous" in result.feedback

    def test_prompt_hook_fails_open_on_llm_error(self, tmp_path: Path) -> None:
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "prompt"
prompt = "Evaluate: {tool_input}"
""")
        mock_cfg = MagicMock()
        runner = HookRunner(tmp_path, cfg=mock_cfg)

        with patch("devagent.core.llm.LLMClient") as MockLLM:
            MockLLM.return_value.complete.side_effect = RuntimeError("no LLM")
            result = runner.pre_tool_use("run_shell", {"command": "ls"})
        assert result.allowed  # fail-open on error

    def test_prompt_template_substitution(self, tmp_path: Path) -> None:
        from devagent.core.llm import LLMResponse
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "prompt"
prompt = "Check this: {tool_input}"
""")
        mock_cfg = MagicMock()
        runner = HookRunner(tmp_path, cfg=mock_cfg)
        captured_messages = []

        def capture(*args, **kwargs):
            captured_messages.extend(args[0])
            return LLMResponse(content='{"ok": true}')

        with patch("devagent.core.llm.LLMClient") as MockLLM:
            MockLLM.return_value.complete.side_effect = capture
            runner.pre_tool_use("run_shell", {"command": "echo hi"})

        assert any("echo hi" in str(m) for m in captured_messages)


# ---------------------------------------------------------------------------
# HookRunner — http hook for lifecycle events
# ---------------------------------------------------------------------------

class TestHttpLifecycleHook:
    def test_http_hook_fires_on_session_start(self, tmp_path: Path) -> None:
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "session_start"
type = "http"
url = "http://localhost:9999/hook"
""")
        runner = HookRunner(tmp_path)
        with patch("devagent.hooks.runner.HookRunner._call_http") as mock_http:
            runner.session_start("test-session-id")
        mock_http.assert_called_once()

    def test_command_hook_still_fires_on_session_start(self, tmp_path: Path) -> None:
        from devagent.hooks.runner import HookRunner
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "session_start"
type = "command"
command = "echo start"
""")
        runner = HookRunner(tmp_path)
        runner.session_start("sid")  # should not raise


# ---------------------------------------------------------------------------
# hooks test CLI — lifecycle events
# ---------------------------------------------------------------------------

class TestHooksTestCLI:
    def test_pre_tool_use_event(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "pre_tool_use"
type = "command"
command = "exit 0"
tool = "run_shell"
""")
        runner = CliRunner()
        result = runner.invoke(app, [
            "hooks", "test", "pre_tool_use",
            "--tool", "run_shell",
            "--project", str(tmp_path),
        ])
        assert result.exit_code == 0

    def test_session_start_lifecycle_event(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        _write_hooks_toml(tmp_path, """
[[hooks]]
event = "session_start"
type = "command"
command = "echo started"
""")
        runner = CliRunner()
        result = runner.invoke(app, [
            "hooks", "test", "session_start",
            "--project", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "lifecycle hook fired" in result.output

    def test_no_hooks_exits_cleanly(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["hooks", "test", "pre_tool_use", "--project", str(tmp_path)])
        assert result.exit_code == 0
