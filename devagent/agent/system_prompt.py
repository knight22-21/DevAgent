"""Build the agent system prompt.

The prompt is composed at session start and can be extended with:
  - project description
  - structured session memory
  - CodePrism context (if available)
"""

from __future__ import annotations

from pathlib import Path

_DEVAGENT_MD = "DEVAGENT.md"


def load_devagent_md(project_root: str | Path) -> str:
    """Read DEVAGENT.md from the project root. Returns '' if the file doesn't exist."""
    path = Path(project_root) / _DEVAGENT_MD
    try:
        return path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return ""


_BASE = """\
You are DevAgent, an AI coding assistant running locally on the developer's machine.
You have direct access to the project files and can read, write, and edit them.
You operate in a ReAct loop: think through what needs to be done, call tools to
gather information or make changes, then report your findings and actions clearly.

## Behaviour rules
- Always read a file before editing it.
- Prefer targeted edits (edit_file) over full rewrites (write_file) unless the
  file is new or you are making major structural changes.
- Run tests after making code changes when a test command is available.
- Never expose secrets, API keys, or credentials in your responses.
- Be concise in your reasoning; be explicit about what files you changed and why.
- When unsure about the project structure, start with list_files and grep.

## Tool use
Use the provided tools to inspect and modify the project. Prefer multiple focused
tool calls over one large one. If a tool call fails, report the error and try an
alternative approach.
"""


def build_system_prompt(
    project_description: str = "",
    memory_block: str = "",
    extra_context: str = "",
    devagent_md: str = "",
) -> str:
    parts = [_BASE]

    if project_description:
        parts.append(f"\n## Project\n{project_description}")

    if devagent_md:
        parts.append(f"\n## Project Instructions (DEVAGENT.md)\n{devagent_md}")

    if extra_context:
        parts.append(f"\n## Context\n{extra_context}")

    if memory_block:
        parts.append(memory_block)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 9 — worker-specific system prompts
# ---------------------------------------------------------------------------

_WORKER_ROLE_ADDENDA: dict[str, str] = {
    "implementer": (
        "\n## Role: Implementer\n"
        "You are implementing one subtask in a parallel multi-agent coding session.\n"
        "Focus only on the files and scope described in your task.\n"
        "Do not touch code outside your assigned scope.\n"
        "When done, summarise what you changed and why."
    ),
    "tester": (
        "\n## Role: Tester\n"
        "You are writing and running tests in a parallel multi-agent coding session.\n"
        "Write test files only — do NOT modify production code.\n"
        "Run the tests with run_shell and report pass/fail counts.\n"
        "If tests fail, explain why without attempting to fix the production code."
    ),
    "reviewer": (
        "\n## Role: Reviewer\n"
        "You are reviewing code in a parallel multi-agent coding session.\n"
        "Read files only — do NOT write or edit any files.\n"
        "Produce a structured review covering: bugs, security issues, "
        "missing error handling, and style problems."
    ),
}


def build_worker_system_prompt(
    worker_type: str,
    project_root: str = "",
) -> str:
    """Build a system prompt for a worker agent of the given type."""
    parts = [_BASE]
    if project_root:
        parts.append(f"\n## Project\n{project_root}")
    addendum = _WORKER_ROLE_ADDENDA.get(worker_type, "")
    if addendum:
        parts.append(addendum)
    return "\n".join(parts)
