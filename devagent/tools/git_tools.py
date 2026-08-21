"""Git tools: status, diff, log, branch info, plus branch/checkout ops.

Intentionally excluded (user handles these): git add, git commit, git push.
Branch creation and checkout are included because the agent needs to work
on feature branches without the user having to pre-create them.
"""

from __future__ import annotations

import subprocess

from devagent.tools.registry import ToolRegistry


def _git(args: list[str], cwd: str, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return err or f"[git exit {result.returncode}]"
        return out or "(no output)"
    except FileNotFoundError:
        return "[error] git not found"
    except subprocess.TimeoutExpired:
        return "[error] git timed out"
    except Exception as exc:
        return f"[error] {exc}"


def register_git_tools(registry: ToolRegistry, project_root: str = ".") -> None:

    def git_status(args: dict) -> str:
        return _git(["status", "--short"], project_root)

    def git_diff(args: dict) -> str:
        path = args.get("path", "")
        staged = args.get("staged", False)
        cmd = ["diff"]
        if staged:
            cmd.append("--staged")
        if path:
            cmd.extend(["--", path])
        return _git(cmd, project_root)

    def git_log(args: dict) -> str:
        n = min(int(args.get("n", 10)), 50)
        format_str = args.get("format", "%h %as %s")
        return _git(["log", f"--max-count={n}", f"--pretty=format:{format_str}"], project_root)

    def git_show(args: dict) -> str:
        ref = args.get("ref", "HEAD")
        path = args.get("path", "")
        cmd = ["show", "--stat", ref]
        if path:
            cmd.extend(["--", path])
        return _git(cmd, project_root)

    def git_branch(args: dict) -> str:
        return _git(["branch", "--show-current"], project_root)

    def git_blame(args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "[error] path is required"
        start = args.get("start_line")
        end = args.get("end_line")
        cmd = ["blame", "--porcelain"]
        if start and end:
            cmd.extend([f"-L{start},{end}"])
        cmd.append(path)
        return _git(cmd, project_root, timeout=30)

    registry.register(
        "git_status",
        "Show the working tree status (modified, untracked, staged files).",
        {"type": "object", "properties": {}},
        git_status,
    )

    registry.register(
        "git_diff",
        "Show diff of changes. Use staged=true for staged changes, path to restrict to a file.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Specific file to diff"},
                "staged": {"type": "boolean", "default": False},
            },
        },
        git_diff,
    )

    registry.register(
        "git_log",
        "Show recent commit history.",
        {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "default": 10, "description": "Number of commits"},
                "format": {"type": "string", "default": "%h %as %s"},
            },
        },
        git_log,
    )

    registry.register(
        "git_show",
        "Show details of a specific commit or HEAD.",
        {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "default": "HEAD"},
                "path": {"type": "string"},
            },
        },
        git_show,
    )

    registry.register(
        "git_branch",
        "Return the current git branch name.",
        {"type": "object", "properties": {}},
        git_branch,
    )

    registry.register(
        "git_blame",
        "Show who last modified each line of a file.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
        },
        git_blame,
    )

    # ------------------------------------------------------------------
    # Write-capable tools (branch management — NOT commit/push)
    # ------------------------------------------------------------------

    def git_branch_create(args: dict) -> str:
        name = args.get("name", "").strip()
        if not name:
            return "[error] branch name is required"
        # Reject names that could be mistaken for remote refs
        if "/" in name and not name.startswith("feat/") and not name.startswith("fix/"):
            pass  # allow e.g. feat/123-my-feature
        from_ref = args.get("from_ref", "")
        cmd = ["checkout", "-b", name]
        if from_ref:
            cmd.append(from_ref)
        return _git(cmd, project_root)

    def git_checkout(args: dict) -> str:
        target = args.get("branch", "").strip() or args.get("target", "").strip()
        if not target:
            return "[error] branch or target is required"
        return _git(["checkout", target], project_root)

    def git_stash(args: dict) -> str:
        action = args.get("action", "push")
        if action == "push":
            msg = args.get("message", "")
            cmd = ["stash", "push"]
            if msg:
                cmd.extend(["-m", msg])
        elif action == "pop":
            cmd = ["stash", "pop"]
        elif action == "list":
            cmd = ["stash", "list"]
        else:
            return f"[error] Unknown stash action: {action!r}. Use push | pop | list"
        return _git(cmd, project_root)

    registry.register(
        "git_branch_create",
        (
            "Create a new git branch and switch to it. "
            "Use from_ref to branch from a specific commit or branch (default: HEAD). "
            "Note: commit and push are the user's responsibility."
        ),
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Branch name, e.g. feat/123-my-feature"},
                "from_ref": {"type": "string", "description": "Starting ref (branch name or commit SHA)"},
            },
            "required": ["name"],
        },
        git_branch_create,
    )

    registry.register(
        "git_checkout",
        "Switch to an existing branch or commit ref.",
        {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Branch name or commit SHA to switch to"},
            },
            "required": ["branch"],
        },
        git_checkout,
    )

    registry.register(
        "git_stash",
        "Stash, pop, or list git stash entries. action: push | pop | list",
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["push", "pop", "list"], "default": "push"},
                "message": {"type": "string", "description": "Stash message (for push)"},
            },
        },
        git_stash,
    )
