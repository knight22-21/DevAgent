"""Rich terminal renderer for the plan mode approval gate."""

from __future__ import annotations

import re

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from devagent.agent.planner import Plan, PlanStep


def render_plan(plan: Plan, console: Console) -> str:
    """Display the plan and return user choice: 'approve' or 'cancel'.

    Loops internally on [E]dit until the user approves or cancels.
    """
    while True:
        _display_plan(plan, console)
        choice = Prompt.ask(
            "[bold][A]pprove[/bold] / [yellow][E]dit[/yellow] / [red][C]ancel[/red]",
            choices=["a", "e", "c", "approve", "edit", "cancel"],
            default="a",
            console=console,
        ).lower()[0]

        if choice == "a":
            return "approve"
        if choice == "c":
            return "cancel"

        # Edit mode
        console.print(
            "[dim]Type edits like:[/dim] [cyan]edit 3: also update the test file[/cyan]  "
            "[dim]or[/dim] [cyan]add: commit changes at the end[/cyan]  "
            "[dim]or[/dim] [cyan]done[/cyan] [dim]to finish editing[/dim]"
        )
        while True:
            raw = console.input("[yellow]edit>[/yellow] ").strip()
            if not raw or raw.lower() == "done":
                break
            _apply_edit(plan, raw, console)


def _display_plan(plan: Plan, console: Console) -> None:
    lines: list[str] = [f"[bold]Task:[/bold] {plan.task}\n"]

    for step in plan.steps:
        hints = f"  [dim]({', '.join(step.tool_hints)})[/dim]" if step.tool_hints else ""
        lines.append(f"  [bold cyan]Step {step.number}[/bold cyan]  {step.description}{hints}")

    lines.append("")

    meta_parts = []
    if plan.estimated_tool_calls:
        meta_parts.append(f"~{plan.estimated_tool_calls} tool calls")
    if plan.estimated_tokens:
        meta_parts.append(f"~{plan.estimated_tokens:,} tokens")
    if meta_parts:
        lines.append(f"  [dim]{' | '.join(meta_parts)}[/dim]")

    console.print()
    console.print(
        Panel(
            "\n".join(lines),
            title="[bold blue]Plan[/bold blue]",
            border_style="blue",
        )
    )


def _apply_edit(plan: Plan, raw: str, console: Console) -> None:
    """Mutate the plan based on an edit command string."""
    # "edit N: new description"
    m = re.match(r"edit\s+(\d+)\s*:\s*(.+)", raw, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        desc = m.group(2).strip()
        for step in plan.steps:
            if step.number == num:
                step.description = desc
                console.print(f"[green]Updated step {num}.[/green]")
                return
        console.print(f"[yellow]Step {num} not found.[/yellow]")
        return

    # "add: description"
    m = re.match(r"add\s*:\s*(.+)", raw, re.IGNORECASE)
    if m:
        desc = m.group(1).strip()
        next_num = max((s.number for s in plan.steps), default=0) + 1
        plan.steps.append(PlanStep(number=next_num, description=desc))
        console.print(f"[green]Added step {next_num}.[/green]")
        return

    # "remove N"
    m = re.match(r"remove\s+(\d+)", raw, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        before = len(plan.steps)
        plan.steps = [s for s in plan.steps if s.number != num]
        if len(plan.steps) < before:
            console.print(f"[green]Removed step {num}.[/green]")
        else:
            console.print(f"[yellow]Step {num} not found.[/yellow]")
        return

    console.print(
        "[dim]Unrecognised edit. Use: edit N: description | add: description | remove N | done[/dim]"
    )


def plan_to_first_message(plan: Plan, original_task: str) -> str:
    """Convert an approved plan into a first message for the agent.

    Prepends the approved plan to the original task so the agent follows it.
    """
    step_lines = "\n".join(
        f"Step {s.number}: {s.description}" for s in plan.steps
    )
    return (
        f"{original_task}\n\n"
        "## Approved Plan\n\n"
        "Follow this plan step by step. Mark each step complete before moving to the next.\n\n"
        f"{step_lines}"
    )
