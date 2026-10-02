"""Git worktree context manager for isolated agent execution."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


class WorktreeError(RuntimeError):
    pass


def _git(args: list[str], cwd: str, *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


@contextmanager
def isolated_worktree(project_root: str | Path, branch_prefix: str = "agent"):
    """Create a temporary git worktree, yield (Path, branch_name), then clean up.

    The yielded path is a fully functional git worktree on a fresh branch that
    diverges from HEAD. After the context exits the worktree directory and temp
    parent are removed. The branch is also deleted unless commits were made.

    Raises WorktreeError if the directory is not a git repository or if
    `git worktree add` fails.
    """
    root = str(Path(project_root).resolve())

    r = _git(["rev-parse", "--git-dir"], cwd=root, check=False)
    if r.returncode != 0:
        raise WorktreeError(f"Not a git repository: {root}")

    base_sha = _git(["rev-parse", "HEAD"], cwd=root).stdout.strip()
    branch = f"{branch_prefix}-{uuid.uuid4().hex[:8]}"
    tmp_parent = tempfile.mkdtemp(prefix="devagent_wt_")
    wt_path = Path(tmp_parent) / branch

    r = _git(["worktree", "add", "-b", branch, str(wt_path)], cwd=root, check=False)
    if r.returncode != 0:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        raise WorktreeError(f"git worktree add failed: {r.stderr.strip()}")

    try:
        yield wt_path, branch
    finally:
        wt_sha_r = _git(["rev-parse", "HEAD"], cwd=str(wt_path), check=False)
        made_commits = (
            wt_sha_r.returncode == 0 and wt_sha_r.stdout.strip() != base_sha
        )
        removed = _git(["worktree", "remove", "--force", str(wt_path)], cwd=root, check=False)
        if removed.returncode != 0:
            # Not fatal — the directory is removed below either way — but say so:
            # a silent failure here is exactly how the stale admin entry appears.
            print(
                f"warning: 'git worktree remove' failed for {wt_path}: "
                f"{removed.stderr.strip() or removed.stdout.strip()}",
                file=sys.stderr,
            )
        shutil.rmtree(tmp_parent, ignore_errors=True)
        # Always prune, after the directory is gone. If `worktree remove` failed
        # (disk error, locked file, NFS timeout) the admin entry under
        # .git/worktrees/ outlives the directory it points at, so `git worktree
        # list` keeps advertising a worktree that no longer exists -- and
        # `git branch -D` then refuses to delete the branch, because it is "used
        # by" that phantom worktree. Pruning first fixes both leaks at once.
        _git(["worktree", "prune"], cwd=root, check=False)
        if not made_commits:
            _git(["branch", "-D", branch], cwd=root, check=False)
