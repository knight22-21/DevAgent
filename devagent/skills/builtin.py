"""Built-in skills shipped with DevAgent."""

from __future__ import annotations

from devagent.skills.loader import Skill

BUILTIN_SKILLS: list[Skill] = [
    Skill(
        name="explain",
        description="Explain what a file or function does",
        prompt=(
            "The user wants you to explain a piece of code clearly and concisely. "
            "Use read_file to read the target, then explain: what it does, why it exists, "
            "key behaviours, important edge cases, and any gotchas. "
            "Do NOT make any changes to files."
        ),
        tools_only=["read_file", "list_files", "grep", "run_shell"],
        model="cheap",
        max_iter=5,
    ),
    Skill(
        name="test",
        description="Run tests for a file and report results",
        prompt=(
            "Run the tests for the specified path. "
            "Use run_shell to run pytest on the target. "
            "Show passing/failing tests. If any fail, describe why they failed. "
            "Do NOT fix them — just report what you found."
        ),
        tools_only=["run_shell", "read_file"],
        model="cheap",
        max_iter=5,
    ),
    Skill(
        name="review",
        description="Review staged git changes before committing",
        prompt=(
            "Review the staged git changes. "
            "Use git_diff to get the diff (staged and unstaged). "
            "Check for: bugs, missing error handling, security issues, missing tests, style problems. "
            "Be specific and constructive — quote the relevant code and suggest fixes. "
            "Do NOT modify any files."
        ),
        tools_only=["git_diff", "git_status", "read_file", "grep"],
        model="reviewing",
        max_iter=8,
    ),
    Skill(
        name="commit",
        description="Stage all changes and commit with a generated message",
        prompt=(
            "Stage all modified files and create a commit. "
            "1. Run git_status to see what changed. "
            "2. Run git_diff to understand the changes. "
            "3. Write a clear conventional commit message (type: description). "
            "4. Show the user the proposed message and ask for confirmation before committing. "
            "5. Run: git add -A && git commit -m '<message>'"
        ),
        tools_only=["git_status", "git_diff", "run_shell"],
        max_iter=5,
    ),
    Skill(
        name="summarize",
        description="Summarize what this session has accomplished",
        prompt=(
            "Summarize what has been accomplished in this session. "
            "Produce a concise summary covering: "
            "(1) what the original task was, "
            "(2) what files were changed and why, "
            "(3) what tests were run and their results, "
            "(4) what remains to be done."
        ),
        tools_only=["read_file", "git_status", "git_diff"],
        model="cheap",
        max_iter=3,
    ),
    Skill(
        name="security",
        description="Show the security gate log for this session",
        prompt="Report the security gate events for this session.",
        tools_only=[],
        max_iter=1,
    ),
    Skill(
        name="help",
        description="Show available skills and commands",
        prompt="List all available skills and explain what each one does.",
        tools_only=[],
        model="cheap",
        max_iter=1,
    ),
]
