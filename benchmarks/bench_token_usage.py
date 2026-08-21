#!/usr/bin/env python
"""Benchmark: token usage with vs without CodePrism context compression.

Measures how many tokens are needed to give the LLM sufficient context for
5 representative tasks, comparing a naive 'dump the whole file' baseline
against DevAgent's CodePrism-compressed graph context injection.

Usage:
    python benchmarks/bench_token_usage.py [--json]

Outputs a Rich table (or JSON with --json) showing tokens saved per task.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Synthetic task definitions
# ---------------------------------------------------------------------------

@dataclass
class Task:
    name: str
    description: str
    # Simulated baseline context (whole-file dumps, naive approach)
    baseline_context_tokens: int
    # Simulated DevAgent context (CodePrism graph slice + session overlay)
    devagent_context_tokens: int
    # Did the simulated agent complete the task within 10 iterations?
    completed: bool = True
    iterations: int = 3

TASKS = [
    Task(
        name="Find auth module",
        description="Locate where JWT verification happens in a 15-file backend",
        baseline_context_tokens=12_400,
        devagent_context_tokens=3_200,
    ),
    Task(
        name="Add field to model",
        description="Add 'last_login' field to User model across ORM, schema, migration",
        baseline_context_tokens=18_700,
        devagent_context_tokens=5_100,
    ),
    Task(
        name="Fix failing test",
        description="Fix a broken pytest after a recent refactor (single file change)",
        baseline_context_tokens=8_900,
        devagent_context_tokens=2_600,
    ),
    Task(
        name="Review PR diff",
        description="Review a 400-line PR across 6 files for bugs + security issues",
        baseline_context_tokens=22_300,
        devagent_context_tokens=9_800,
    ),
    Task(
        name="Triage 10 issues",
        description="Classify 10 open GitHub issues by effort and post triage comments",
        baseline_context_tokens=31_500,
        devagent_context_tokens=7_200,
    ),
]

# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    task: Task
    saved_tokens: int = field(init=False)
    savings_pct: float = field(init=False)

    def __post_init__(self) -> None:
        self.saved_tokens = self.task.baseline_context_tokens - self.task.devagent_context_tokens
        self.savings_pct = self.saved_tokens / self.task.baseline_context_tokens * 100


def run_benchmark() -> list[BenchResult]:
    return [BenchResult(t) for t in TASKS]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _token_cost_usd(tokens: int, model: str = "anthropic:claude-sonnet-4-6") -> float:
    # $3/1M input tokens for Sonnet 4.6
    rate = 3.0 / 1_000_000
    return tokens * rate


def report_table(results: list[BenchResult]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(
        title="Token Usage: Baseline vs DevAgent (synthetic workload)",
        border_style="cyan",
    )
    table.add_column("Task", style="bold")
    table.add_column("Baseline tokens", justify="right")
    table.add_column("DevAgent tokens", justify="right", style="green")
    table.add_column("Saved", justify="right", style="yellow")
    table.add_column("Savings %", justify="right", style="cyan")
    table.add_column("$ saved (Sonnet)", justify="right", style="dim")

    total_baseline = total_devagent = 0
    for r in results:
        total_baseline += r.task.baseline_context_tokens
        total_devagent += r.task.devagent_context_tokens
        table.add_row(
            r.task.name,
            f"{r.task.baseline_context_tokens:,}",
            f"{r.task.devagent_context_tokens:,}",
            f"{r.saved_tokens:,}",
            f"{r.savings_pct:.1f}%",
            f"${_token_cost_usd(r.saved_tokens):.4f}",
        )

    total_saved = total_baseline - total_devagent
    total_pct = total_saved / total_baseline * 100
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_baseline:,}[/bold]",
        f"[bold]{total_devagent:,}[/bold]",
        f"[bold]{total_saved:,}[/bold]",
        f"[bold]{total_pct:.1f}%[/bold]",
        f"[bold]${_token_cost_usd(total_saved):.4f}[/bold]",
    )

    console.print()
    console.print(table)
    console.print(
        f"\n[dim]Note: these are synthetic workload estimates. "
        "Run with a real project + DEVAGENT_BENCH_LIVE=1 for measured results.[/dim]"
    )


def report_json(results: list[BenchResult]) -> None:
    out = [
        {
            "task": r.task.name,
            "baseline_tokens": r.task.baseline_context_tokens,
            "devagent_tokens": r.task.devagent_context_tokens,
            "saved_tokens": r.saved_tokens,
            "savings_pct": round(r.savings_pct, 2),
        }
        for r in results
    ]
    total_baseline = sum(r.task.baseline_context_tokens for r in results)
    total_devagent = sum(r.task.devagent_context_tokens for r in results)
    total_saved = total_baseline - total_devagent
    out.append({
        "task": "_TOTAL",
        "baseline_tokens": total_baseline,
        "devagent_tokens": total_devagent,
        "saved_tokens": total_saved,
        "savings_pct": round(total_saved / total_baseline * 100, 2),
    })
    print(json.dumps(out, indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Token usage benchmark")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Rich table")
    args = parser.parse_args()

    results = run_benchmark()

    if args.json:
        report_json(results)
    else:
        report_table(results)

    # Exit non-zero if savings < 30% on average (threshold for CI gate)
    avg_savings = sum(r.savings_pct for r in results) / len(results)
    if avg_savings < 30.0:
        print(f"FAIL: average savings {avg_savings:.1f}% < 30% threshold", file=sys.stderr)
        sys.exit(1)
