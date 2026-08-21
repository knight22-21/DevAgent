"""Rich terminal renderer for the agent loop event stream.

Consumes AgentEvent objects from agent.loop.AgentLoop.run() and renders
them using Rich panels, spinners, and syntax highlighting.
"""

from __future__ import annotations

import json
from typing import Generator

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from devagent.agent.loop import (
    AgentEvent,
    BudgetWarningEvent,
    ErrorEvent,
    FinalAnswerEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)

console = Console()


def render_events(events: Generator[AgentEvent, None, None]) -> str:
    """Render a stream of agent events to the terminal.

    Returns the final text answer (or empty string on error).
    """
    final_text = ""
    for event in events:
        if isinstance(event, ThinkingEvent):
            _render_thinking(event)
        elif isinstance(event, ToolCallEvent):
            _render_tool_call(event)
        elif isinstance(event, ToolResultEvent):
            _render_tool_result(event)
        elif isinstance(event, FinalAnswerEvent):
            _render_final_answer(event)
            final_text = event.text
        elif isinstance(event, BudgetWarningEvent):
            _render_budget_warning(event)
        elif isinstance(event, ErrorEvent):
            _render_error(event)
    return final_text


def _render_thinking(event: ThinkingEvent) -> None:
    """Render reasoning/thinking text in a subtle style."""
    if not event.text.strip():
        return
    console.print()
    console.print(Markdown(event.text))


def _render_tool_call(event: ToolCallEvent) -> None:
    """Render a tool call with its arguments."""
    args_str = json.dumps(event.args, indent=2) if event.args else "{}"
    # Truncate very long args for readability
    if len(args_str) > 400:
        args_str = args_str[:400] + "\n  ... (truncated)"
    label = Text.assemble(
        Text("  Calling ", style="dim"),
        Text(event.name, style="bold cyan"),
        Text(f"  #{event.id[:6]}", style="dim"),
    )
    console.print()
    console.print(label)
    if event.args:
        console.print(Text(args_str, style="dim"))


def _render_tool_result(event: ToolResultEvent) -> None:
    """Render a tool result, truncated if very long."""
    result = event.result
    style = "green" if event.success else "red"
    prefix = "[OK]" if event.success else "[ERR]"

    # Truncate long output
    max_lines = 30
    lines = result.splitlines()
    if len(lines) > max_lines:
        shown = "\n".join(lines[:max_lines])
        result = f"{shown}\n... ({len(lines) - max_lines} more lines)"

    console.print(
        Panel(
            Text(result, style="dim"),
            title=Text.assemble(Text(prefix + " ", style=style), Text(event.name, style="bold")),
            border_style=style,
            expand=False,
        )
    )


def _render_final_answer(event: FinalAnswerEvent) -> None:
    """Render the final LLM answer with token usage footer."""
    console.print()
    console.print(Rule(style="bright_blue"))
    console.print(Markdown(event.text))
    console.print()
    if event.tokens_in or event.tokens_out:
        console.print(
            Text(
                f"  tokens: {event.tokens_in} in / {event.tokens_out} out",
                style="dim",
            )
        )


def _render_budget_warning(event: BudgetWarningEvent) -> None:
    pct = f"{event.used / event.limit * 100:.0f}%" if event.limit else "?"
    console.print(
        Text(
            f"  [budget] {event.used:,} / {event.limit:,} tokens used ({pct})",
            style="yellow",
        )
    )


def _render_error(event: ErrorEvent) -> None:
    console.print()
    console.print(
        Panel(event.message, title="[bold red]Agent Error[/bold red]", border_style="red")
    )
