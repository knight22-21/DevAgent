#!/usr/bin/env python
"""Benchmark: task completion rate using a mock LLM.

Simulates 10 agent tasks end-to-end. The LLM is replaced by a deterministic
mock that calls the right tools in sequence. We measure:
  - Did the task complete (reach FinalAnswerEvent)?
  - How many iterations did it take?
  - Token budget consumed

Target: 9/10 tasks complete within MAX_ITERATIONS=30 (1 may legitimately timeout).

Usage:
    python benchmarks/bench_tasks.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

@dataclass
class TaskSpec:
    name: str
    description: str
    # Tool sequence the mock LLM will request
    tool_sequence: list[tuple[str, dict]]
    # Expected to complete within MAX_ITERATIONS
    should_complete: bool = True


TASK_SPECS: list[TaskSpec] = [
    TaskSpec(
        name="Read + explain file",
        description="Read a module and explain what it does",
        tool_sequence=[("read_file", {"path": "src/utils.py"})],
    ),
    TaskSpec(
        name="Find symbol definition",
        description="Find where AuthMiddleware is defined",
        tool_sequence=[
            ("grep", {"pattern": "class AuthMiddleware", "path": "."}),
            ("read_file", {"path": "src/auth.py"}),
        ],
    ),
    TaskSpec(
        name="Edit + write file",
        description="Add a logging call to an existing function",
        tool_sequence=[
            ("read_file", {"path": "src/handler.py"}),
            ("edit_file", {"path": "src/handler.py", "old_string": "def handle(", "new_string": "def handle("}),
        ],
    ),
    TaskSpec(
        name="Run tests",
        description="Execute the test suite and report failures",
        tool_sequence=[
            ("run_shell", {"command": "python -m pytest tests/ -q 2>&1"}),
        ],
    ),
    TaskSpec(
        name="Git status + diff",
        description="Show what changed since last commit",
        tool_sequence=[
            ("run_shell", {"command": "git status --short"}),
            ("git_diff", {"args": "HEAD"}),
        ],
    ),
    TaskSpec(
        name="Create new module",
        description="Create a new utility module with a helper function",
        tool_sequence=[
            ("write_file", {"path": "src/helpers.py", "content": "def helper(): pass\n"}),
            ("run_shell", {"command": "python -c 'import src.helpers'"}),
        ],
    ),
    TaskSpec(
        name="Search + replace across files",
        description="Rename a function across all files",
        tool_sequence=[
            ("grep", {"pattern": "old_function_name", "path": "."}),
            ("edit_file", {"path": "src/a.py", "old_string": "old_function_name", "new_string": "new_function_name"}),
            ("edit_file", {"path": "src/b.py", "old_string": "old_function_name", "new_string": "new_function_name"}),
        ],
    ),
    TaskSpec(
        name="Remember + recall facts",
        description="Store a discovery and recall it later",
        tool_sequence=[
            ("remember_fact", {"key": "auth_path", "value": "src/auth.py"}),
            ("recall_facts", {}),
            ("read_file", {"path": "src/auth.py"}),
        ],
    ),
    TaskSpec(
        name="List files + summarise",
        description="List all Python files in src/ and summarise their purpose",
        tool_sequence=[
            ("list_files", {"path": "src"}),
            ("read_file", {"path": "src/main.py"}),
        ],
    ),
    TaskSpec(
        name="Multi-step refactor",
        description="Extract a function into a helper module (read, create, edit, test)",
        tool_sequence=[
            ("read_file", {"path": "src/big.py"}),
            ("write_file", {"path": "src/extracted.py", "content": "def extracted(): pass\n"}),
            ("edit_file", {"path": "src/big.py", "old_string": "def extracted():", "new_string": "from src.extracted import extracted\n"}),
            ("run_shell", {"command": "python -m pytest tests/ -x -q"}),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Mock LLM that plays back a tool sequence
# ---------------------------------------------------------------------------

def _make_mock_llm_response(tool_calls: list[tuple[str, dict]], final: bool = False):
    from devagent.core.llm import LLMResponse, ToolCallRequest
    if final or not tool_calls:
        return LLMResponse(
            content="Task completed successfully.",
            tool_calls=[],
            input_tokens=50,
            output_tokens=20,
        )
    tc_name, tc_args = tool_calls[0]
    return LLMResponse(
        content="",
        tool_calls=[ToolCallRequest(id=uuid.uuid4().hex[:8], name=tc_name, args=tc_args)],
        input_tokens=200,
        output_tokens=30,
    )


# ---------------------------------------------------------------------------
# Simulated task runner
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    spec: TaskSpec
    completed: bool
    iterations: int
    tokens_used: int
    error: str = ""


def _run_task(spec: TaskSpec) -> TaskResult:
    """Simulate running a task with a mock LLM and a stubbed tool registry."""
    from devagent.agent.loop import AgentLoop, FinalAnswerEvent, ErrorEvent, MAX_ITERATIONS
    from devagent.tools.registry import ToolRegistry
    from devagent.session.manager import SessionManager
    from devagent.session.memory import MemoryBlock
    from devagent.session.budget import TokenBudget

    # Build a minimal registry (stub handlers that return canned responses)
    registry = ToolRegistry()
    _STUB_RESULT = "OK: stub result"
    for tool_name in [
        "read_file", "write_file", "edit_file", "list_files", "find_files",
        "grep", "run_shell", "git_diff", "git_log", "git_show",
        "remember_fact", "recall_facts", "forget_fact",
    ]:
        registry.register(
            tool_name, "stub", {"type": "object", "properties": {}},
            lambda args, _n=tool_name: _STUB_RESULT,
        )

    # Mock LLM that plays back the tool sequence then gives a final answer
    remaining_calls = list(spec.tool_sequence)
    mock_llm = MagicMock()

    def _complete_side_effect(messages, tools):
        nonlocal remaining_calls
        if remaining_calls:
            call = remaining_calls.pop(0)
            return _make_mock_llm_response([call])
        return _make_mock_llm_response([], final=True)

    mock_llm.complete_with_tools.side_effect = _complete_side_effect
    mock_llm.cfg = MagicMock()
    mock_llm.cfg.provider = "mock"
    mock_llm.cfg.model = "mock-llm"

    # Build the loop
    session_mgr = MagicMock()
    session_mgr.get_events.return_value = []
    session_mgr.get_token_totals.return_value = {"tokens_in": 0, "tokens_out": 0}

    memory = MagicMock()
    memory.as_prompt_block.return_value = ""

    budget = TokenBudget()
    loop = AgentLoop(
        llm=mock_llm,
        registry=registry,
        session_mgr=session_mgr,
        session_id="bench",
        memory=memory,
        budget=budget,
        system_prompt="You are a coding agent.",
        codeprism_client=None,
        router=None,
    )

    # Patch build_messages to return minimal message list
    from devagent.core.llm import AgentMessage
    import devagent.agent.loop as loop_mod
    original_build = loop_mod.build_messages
    loop_mod.build_messages = lambda sid, sys_p, **kw: [AgentMessage(role="system", content=sys_p), AgentMessage(role="user", content=spec.description)]

    try:
        completed = False
        error = ""
        iterations = 0
        for event in loop.run(spec.description):
            if isinstance(event, FinalAnswerEvent):
                completed = True
                iterations = loop_mod.MAX_ITERATIONS  # upper bound; actual is tracked by loop
            elif isinstance(event, ErrorEvent):
                error = event.message
    finally:
        loop_mod.build_messages = original_build

    # Approximate iterations from LLM call count
    iterations = mock_llm.complete_with_tools.call_count
    tokens = budget.total_used

    return TaskResult(
        spec=spec,
        completed=completed,
        iterations=iterations,
        tokens_used=tokens,
        error=error,
    )


def run_benchmark() -> list[TaskResult]:
    return [_run_task(spec) for spec in TASK_SPECS]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_table(results: list[TaskResult]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Task Completion Rate", border_style="cyan")
    table.add_column("Task", style="bold", max_width=35)
    table.add_column("Complete?", justify="center")
    table.add_column("Iterations", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Notes")

    for r in results:
        status = "[green]YES[/green]" if r.completed else "[red]NO[/red]"
        notes = r.error[:40] if r.error else ""
        table.add_row(r.spec.name, status, str(r.iterations), f"{r.tokens_used:,}", notes)

    console.print()
    console.print(table)

    completed = sum(1 for r in results if r.completed)
    total = len(results)
    rate = completed / total * 100
    console.print(f"\n[bold]Completion rate: {completed}/{total} ({rate:.1f}%)[/bold]")
    console.print(f"[dim]Total tokens across all tasks: {sum(r.tokens_used for r in results):,}[/dim]")


def report_json(results: list[TaskResult]) -> None:
    completed = sum(1 for r in results if r.completed)
    total = len(results)
    print(json.dumps({
        "completion_rate_pct": round(completed / total * 100, 2),
        "completed": completed,
        "total": total,
        "total_tokens": sum(r.tokens_used for r in results),
        "tasks": [
            {
                "name": r.spec.name,
                "completed": r.completed,
                "iterations": r.iterations,
                "tokens": r.tokens_used,
                "error": r.error,
            }
            for r in results
        ],
    }, indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task completion benchmark")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = run_benchmark()

    if args.json:
        report_json(results)
    else:
        report_table(results)

    completed = sum(1 for r in results if r.completed)
    total = len(results)
    # Target: at least 9/10 (90%)
    if completed < (total * 9 // 10):
        print(f"FAIL: only {completed}/{total} tasks completed (target: {total * 9 // 10})", file=sys.stderr)
        sys.exit(1)
