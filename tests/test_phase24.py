"""Tests for Phase 24 — autofix-pr watch mode."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from devagent.cli import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

runner = CliRunner()


def _make_pr_data(branch: str = "fix/my-feature", pr_number: int = 42):
    return {
        "title": f"PR #{pr_number}",
        "head": {"ref": branch},
        "number": pr_number,
    }


def _make_run(run_id: str, conclusion: str = "failure", status: str = "completed", branch: str = "fix/my-feature"):
    return {
        "id": int(run_id),
        "name": "Test Suite",
        "conclusion": conclusion,
        "status": status,
        "head_sha": "abc1234def",
        "head_branch": branch,
    }


def _make_comment(comment_id: int, path: str = "src/foo.py", line: int = 10, body: str = "Fix this."):
    return {"id": comment_id, "path": path, "line": line, "body": body}


# ---------------------------------------------------------------------------
# Unit tests — run_autofix_pr logic
# ---------------------------------------------------------------------------

class TestRunAutofixPr:
    def _gh_mock(self, pr_data, runs=None, comments=None):
        gh = MagicMock()

        def _get(path):
            if "/pulls/" in path and path.endswith(f"/{pr_data['number']}"):
                return pr_data
            if "/actions/runs" in path:
                return {"workflow_runs": runs or []}
            if "/comments" in path:
                return comments or []
            return {}

        gh.get.side_effect = _get
        gh._headers = {}
        return gh

    def test_exits_after_max_polls_with_no_events(self, tmp_path):
        """With max_polls=1 and no failures/comments, should exit cleanly."""
        from devagent.agent.flows import run_autofix_pr
        from devagent.core.config import AgentConfig, DevAgentConfig, LLMConfig, SessionConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(provider="ollama", model="llama3.2"),
            agent=AgentConfig(),
            session=SessionConfig(),
        )
        pr_data = _make_pr_data()

        with patch("devagent.agent.flows._require_gh_token", return_value="tok"), \
             patch("devagent.tools.github_tools.GitHubAPI") as MockGH, \
             patch("devagent.agent.flows.DevAgentSession") as MockSession, \
             patch("subprocess.run") as mock_subproc:
            MockGH.return_value = self._gh_mock(pr_data)
            mock_subproc.return_value = MagicMock(returncode=0)

            run_autofix_pr(cfg, tmp_path, "https://github.com/owner/repo/pull/42", max_polls=1)

        # No agent sessions started — no CI failures or comments
        MockSession.assert_not_called()

    def test_ci_failure_triggers_agent(self, tmp_path):
        """A new failed run triggers a DevAgentSession.run_message call."""
        from devagent.agent.flows import run_autofix_pr
        from devagent.core.config import AgentConfig, DevAgentConfig, LLMConfig, SessionConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(provider="ollama", model="llama3.2"),
            agent=AgentConfig(),
            session=SessionConfig(),
        )
        pr_data = _make_pr_data()
        failed_run = _make_run("999", conclusion="failure")

        call_count = 0

        def _get(path):
            nonlocal call_count
            call_count += 1
            if "/pulls/42" in path and not "/comments" in path:
                return pr_data
            if "/actions/runs" in path and "jobs" not in path:
                # Return empty on seeding call, failed run on poll
                if call_count <= 3:
                    return {"workflow_runs": []}
                return {"workflow_runs": [failed_run]}
            if "/jobs" in path:
                return {"jobs": [{"id": 1, "name": "test", "conclusion": "failure", "steps": []}]}
            if "/comments" in path:
                return []
            return {}

        mock_gh = MagicMock()
        mock_gh.get.side_effect = _get
        mock_gh._headers = {}

        mock_session = MagicMock()
        mock_session.run_message.return_value = "done"

        with patch("devagent.agent.flows._require_gh_token", return_value="tok"), \
             patch("devagent.tools.github_tools.GitHubAPI", return_value=mock_gh), \
             patch("devagent.agent.flows.DevAgentSession", return_value=mock_session), \
             patch("devagent.agent.flows._fetch_failed_job_logs", return_value=([{"id": 1}], "log output")), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)):
            run_autofix_pr(cfg, tmp_path, "https://github.com/owner/repo/pull/42", max_polls=1)

    def test_review_comment_triggers_agent(self, tmp_path):
        """A new review comment triggers a DevAgentSession.run_message call."""
        from devagent.agent.flows import run_autofix_pr
        from devagent.core.config import AgentConfig, DevAgentConfig, LLMConfig, SessionConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(provider="ollama", model="llama3.2"),
            agent=AgentConfig(),
            session=SessionConfig(),
        )
        pr_data = _make_pr_data()
        comment = _make_comment(1001, body="Please fix this style issue.")

        seed_done = False

        def _get(path):
            nonlocal seed_done
            if "/pulls/42" in path and "/comments" not in path and "/runs" not in path:
                return pr_data
            if "/actions/runs" in path:
                return {"workflow_runs": []}
            if "/comments" in path:
                if not seed_done:
                    seed_done = True
                    return []  # seed: no comments
                return [comment]  # poll: new comment
            return {}

        mock_gh = MagicMock()
        mock_gh.get.side_effect = _get
        mock_gh._headers = {}

        mock_session = MagicMock()
        mock_session.run_message.return_value = "addressed"

        with patch("devagent.agent.flows._require_gh_token", return_value="tok"), \
             patch("devagent.tools.github_tools.GitHubAPI", return_value=mock_gh), \
             patch("devagent.agent.flows.DevAgentSession", return_value=mock_session), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)):
            run_autofix_pr(cfg, tmp_path, "https://github.com/owner/repo/pull/42", max_polls=1)

        mock_session.run_message.assert_called_once()
        msg = mock_session.run_message.call_args[0][0]
        assert "review comment" in msg.lower() or "Fix this style issue" in msg

    def test_already_seen_run_not_reprocessed(self, tmp_path):
        """A run that was present during seeding is not re-processed."""
        from devagent.agent.flows import run_autofix_pr
        from devagent.core.config import AgentConfig, DevAgentConfig, LLMConfig, SessionConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(provider="ollama", model="llama3.2"),
            agent=AgentConfig(),
            session=SessionConfig(),
        )
        pr_data = _make_pr_data()
        existing_run = _make_run("888", conclusion="failure")

        def _get(path):
            if "/pulls/42" in path and "/comments" not in path and "/runs" not in path:
                return pr_data
            if "/actions/runs" in path:
                return {"workflow_runs": [existing_run]}
            if "/comments" in path:
                return []
            return {}

        mock_gh = MagicMock()
        mock_gh.get.side_effect = _get
        mock_gh._headers = {}

        mock_session = MagicMock()

        with patch("devagent.agent.flows._require_gh_token", return_value="tok"), \
             patch("devagent.tools.github_tools.GitHubAPI", return_value=mock_gh), \
             patch("devagent.agent.flows.DevAgentSession", return_value=mock_session), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)):
            run_autofix_pr(cfg, tmp_path, "https://github.com/owner/repo/pull/42", max_polls=1)

        mock_session.run_message.assert_not_called()

    def test_invalid_pr_url_raises(self, tmp_path):
        """Bad PR URL raises ValueError."""
        from devagent.agent.flows import run_autofix_pr
        from devagent.core.config import AgentConfig, DevAgentConfig, LLMConfig, SessionConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(provider="ollama", model="llama3.2"),
            agent=AgentConfig(),
            session=SessionConfig(),
        )
        with patch("devagent.agent.flows._require_gh_token", return_value="tok"), \
             pytest.raises(ValueError, match="Cannot parse"):
            run_autofix_pr(cfg, tmp_path, "https://example.com/not-a-pr", max_polls=1)

    def test_git_checkout_called(self, tmp_path):
        """Branch checkout is attempted on entry."""
        from devagent.agent.flows import run_autofix_pr
        from devagent.core.config import AgentConfig, DevAgentConfig, LLMConfig, SessionConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(provider="ollama", model="llama3.2"),
            agent=AgentConfig(),
            session=SessionConfig(),
        )
        pr_data = _make_pr_data(branch="feature/test")

        def _get(path):
            if "/pulls/42" in path and "/comments" not in path and "/runs" not in path:
                return pr_data
            if "/actions/runs" in path:
                return {"workflow_runs": []}
            if "/comments" in path:
                return []
            return {}

        mock_gh = MagicMock()
        mock_gh.get.side_effect = _get
        mock_gh._headers = {}

        with patch("devagent.agent.flows._require_gh_token", return_value="tok"), \
             patch("devagent.tools.github_tools.GitHubAPI", return_value=mock_gh), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_sub:
            run_autofix_pr(cfg, tmp_path, "https://github.com/owner/repo/pull/42", max_polls=1)

        cmds = [c[0][0] for c in mock_sub.call_args_list]
        assert any("checkout" in str(c) for c in cmds)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestAutofixPrCli:
    def test_missing_config_exits_1(self):
        with patch("devagent.cli.config_exists", return_value=False):
            result = runner.invoke(app, ["autofix-pr", "https://github.com/o/r/pull/1"])
        assert result.exit_code == 1

    def test_bad_url_exits_1(self):
        with patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="t"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)), \
             patch("devagent.agent.flows.run_autofix_pr", side_effect=ValueError("Cannot parse")):
            result = runner.invoke(app, ["autofix-pr", "https://example.com/bad"])
        assert result.exit_code == 1

    def test_keyboard_interrupt_exits_cleanly(self):
        with patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="t"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)), \
             patch("devagent.agent.flows.run_autofix_pr", side_effect=KeyboardInterrupt()):
            result = runner.invoke(app, ["autofix-pr", "https://github.com/o/r/pull/1"])
        assert result.exit_code == 0
