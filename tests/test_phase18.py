"""Phase 18 — Git worktree isolation tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from devagent.agent.worktree import WorktreeError, isolated_worktree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_git_repo(path: Path) -> None:
    """Initialise a minimal git repo with one commit so HEAD exists."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], capture_output=True, check=True)


# ---------------------------------------------------------------------------
# WorktreeError on non-git directory
# ---------------------------------------------------------------------------

class TestWorktreeErrorOnNonGitDir:
    def test_raises_on_plain_dir(self, tmp_path: Path) -> None:
        r = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "--git-dir"],
            capture_output=True,
        )
        if r.returncode == 0:
            pytest.skip("tmp_path is inside a git repo on this system")
        with pytest.raises(WorktreeError, match="Not a git repository"), isolated_worktree(tmp_path):
            pass


# ---------------------------------------------------------------------------
# Happy path — worktree created, yields valid path, cleans up
# ---------------------------------------------------------------------------

class TestIsolatedWorktreeHappyPath:
    def test_yields_existing_path(self, tmp_path: Path) -> None:
        _make_git_repo(tmp_path)
        with isolated_worktree(tmp_path, branch_prefix="test") as (wt_path, branch):
            assert wt_path.is_dir(), "worktree path should exist inside context"
            assert branch.startswith("test-")

    def test_worktree_removed_after_context(self, tmp_path: Path) -> None:
        _make_git_repo(tmp_path)
        with isolated_worktree(tmp_path, branch_prefix="test") as (wt_path, _):
            captured_path = wt_path
        assert not captured_path.exists(), "worktree should be cleaned up after context"

    def test_branch_deleted_when_no_commits(self, tmp_path: Path) -> None:
        _make_git_repo(tmp_path)
        with isolated_worktree(tmp_path, branch_prefix="test") as (_, branch):
            captured_branch = branch
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--list", captured_branch],
            capture_output=True,
            text=True,
        )
        assert captured_branch not in result.stdout, "unused branch should be deleted"

    def test_branch_retained_when_commits_made(self, tmp_path: Path) -> None:
        _make_git_repo(tmp_path)
        with isolated_worktree(tmp_path, branch_prefix="test") as (wt_path, branch):
            captured_branch = branch
            (wt_path / "new.txt").write_text("change")
            subprocess.run(["git", "-C", str(wt_path), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(wt_path), "commit", "-m", "change"],
                capture_output=True,
                check=True,
            )
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--list", captured_branch],
            capture_output=True,
            text=True,
        )
        assert captured_branch in result.stdout, "branch with commits should be kept"
        # clean up branch so the repo stays tidy
        subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "-D", captured_branch],
            capture_output=True,
        )

    def test_exception_in_body_still_cleans_up(self, tmp_path: Path) -> None:
        _make_git_repo(tmp_path)
        captured_path: Path | None = None
        with pytest.raises(RuntimeError), isolated_worktree(tmp_path, branch_prefix="test") as (wt_path, _):
            captured_path = wt_path
            raise RuntimeError("simulated failure")
        assert captured_path is not None
        assert not captured_path.exists(), "worktree should be cleaned up even on exception"


# ---------------------------------------------------------------------------
# AgentDef loader — isolation field round-trip
# ---------------------------------------------------------------------------

class TestAgentDefIsolationField:
    def test_default_is_empty_string(self) -> None:
        from devagent.agents.loader import AgentDef
        ad = AgentDef(name="test")
        assert ad.isolation == ""

    def test_isolation_worktree_accepted(self) -> None:
        from devagent.agents.loader import AgentDef
        ad = AgentDef(name="test", isolation="worktree")
        assert ad.isolation == "worktree"

    def test_load_from_toml(self, tmp_path: Path) -> None:
        from devagent.agents.loader import load_agent_defs
        agents_dir = tmp_path / ".devagent" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "myagent.toml").write_text(
            'name = "myagent"\nisolation = "worktree"\n'
        )
        defs = load_agent_defs(tmp_path)
        assert "myagent" in defs
        assert defs["myagent"].isolation == "worktree"


# ---------------------------------------------------------------------------
# Cleanup when `git worktree remove` fails
# ---------------------------------------------------------------------------

def _worktree_entries(root: Path) -> list[str]:
    """`git worktree list --porcelain` entries, counted rather than path-matched.

    Matching on the path spelling is unreliable on Windows: the same directory can
    be reported as ``C:/Users/ADMINI~1/...`` (8.3 short form) in one place and
    ``C:/Users/Administrator/...`` in another, which makes a "path not in listing"
    assertion pass for the wrong reason.
    """
    out = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    ).stdout
    return [block for block in out.split("\n\n") if block.strip()]


def _git_branches(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "branch", "--list"],
        capture_output=True,
        text=True,
    ).stdout


def _fail_worktree_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `git worktree remove` fail while leaving every other git call real."""
    import devagent.agent.worktree as wtmod

    real_git = wtmod._git

    def flaky(args, cwd, *, check=True):  # type: ignore[no-untyped-def]
        if args[:2] == ["worktree", "remove"]:
            return subprocess.CompletedProcess(
                args, 1, stdout="", stderr="simulated: remove failed"
            )
        return real_git(args, cwd, check=check)

    monkeypatch.setattr(wtmod, "_git", flaky)


class TestCleanupWhenWorktreeRemoveFails:
    def test_no_stale_admin_entry_after_failed_remove(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_git_repo(tmp_path)
        _fail_worktree_remove(monkeypatch)

        with isolated_worktree(tmp_path, branch_prefix="test") as (wt_path, _):
            captured_path = wt_path

        assert not captured_path.exists(), "directory should still be removed"
        entries = _worktree_entries(tmp_path)
        assert len(entries) == 1, (
            f"only the main worktree should remain, got {len(entries)}:\n"
            + "\n".join(entries)
        )
        assert "prunable" not in "\n".join(entries)

    def test_branch_not_leaked_when_remove_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_git_repo(tmp_path)
        _fail_worktree_remove(monkeypatch)

        with isolated_worktree(tmp_path, branch_prefix="test") as (_, branch):
            captured_branch = branch

        # Without the prune, `git branch -D` refuses ("used by worktree at ...")
        # and the branch survives as an orphaned ref.
        assert captured_branch not in _git_branches(tmp_path), (
            "with no commits the branch should be deleted even when remove failed"
        )

    def test_failure_is_reported_on_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        _make_git_repo(tmp_path)
        _fail_worktree_remove(monkeypatch)

        with isolated_worktree(tmp_path, branch_prefix="test"):
            pass

        assert "worktree remove" in capsys.readouterr().err

    def test_happy_path_still_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Control: with no injected failure nothing is warned about."""
        _make_git_repo(tmp_path)

        with isolated_worktree(tmp_path, branch_prefix="test") as (wt_path, _):
            captured_path = wt_path

        assert not captured_path.exists()
        assert "worktree remove" not in capsys.readouterr().err
        assert len(_worktree_entries(tmp_path)) == 1
