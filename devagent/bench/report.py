"""BenchReport — formats task results as Rich tables and JSON."""

from __future__ import annotations

import json
from pathlib import Path

from devagent.bench.runner import TaskResult

_RESULTS_DIR = Path(__file__).parent.parent.parent / "benchmarks" / "results"


class BenchReport:
    """Render benchmark results to the terminal or save as JSON."""

    @staticmethod
    def render_table(results: list[TaskResult]) -> None:
        """Print a Rich table of individual task results."""
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Benchmark Results", show_lines=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Pass", justify="center")
        table.add_column("Iter", justify="right")
        table.add_column("Cost $", justify="right")
        table.add_column("Time (s)", justify="right")
        table.add_column("Error / Output", style="dim", max_width=50)

        for r in results:
            status = "[green]ok[/green]" if r.passed else "[red]FAIL[/red]"
            detail = r.error or r.oracle_output or ""
            table.add_row(
                r.task_id,
                status,
                str(r.iterations_used) if r.iterations_used else "-",
                f"{r.cost_usd:.4f}" if r.cost_usd else "-",
                f"{r.duration_sec:.1f}",
                detail[:80],
            )

        console.print(table)

    @staticmethod
    def render_summary(results: list[TaskResult]) -> None:
        """Print a summary line: pass rate, avg cost, avg time."""
        from rich.console import Console

        console = Console()
        if not results:
            console.print("[yellow]No results to summarise.[/yellow]")
            return

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        rate = passed / total * 100
        avg_cost = sum(r.cost_usd for r in results) / total
        avg_time = sum(r.duration_sec for r in results) / total
        avg_iter = sum(r.iterations_used for r in results) / total

        color = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
        console.print(
            f"\n[bold]Summary:[/bold] "
            f"[{color}]{passed}/{total} passed ({rate:.0f}%)[/{color}] | "
            f"avg cost ${avg_cost:.4f} | "
            f"avg time {avg_time:.1f}s | "
            f"avg iterations {avg_iter:.1f}"
        )

    @staticmethod
    def render_by_category(results: list[TaskResult], tasks_by_id: dict) -> None:
        """Print pass rate broken down by category."""
        from collections import defaultdict

        from rich.console import Console
        from rich.table import Table

        console = Console()
        by_cat: dict[str, list[TaskResult]] = defaultdict(list)
        for r in results:
            cat = tasks_by_id.get(r.task_id, {}).get("category", "unknown")
            by_cat[cat].append(r)

        table = Table(title="Results by Category")
        table.add_column("Category", style="cyan")
        table.add_column("Passed", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Pass Rate", justify="right")

        for cat, cat_results in sorted(by_cat.items()):
            p = sum(1 for r in cat_results if r.passed)
            t = len(cat_results)
            rate = p / t * 100
            color = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
            table.add_row(cat, str(p), str(t), f"[{color}]{rate:.0f}%[/{color}]")

        console.print(table)

    @staticmethod
    def save_json(results: list[TaskResult], label: str = "bench") -> Path:
        """Save results to benchmarks/results/<label>_<timestamp>.json."""
        import datetime

        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d_%H%M%S")
        path = _RESULTS_DIR / f"{label}_{ts}.json"
        data = [
            {
                "task_id": r.task_id,
                "passed": r.passed,
                "duration_sec": round(r.duration_sec, 2),
                "iterations_used": r.iterations_used,
                "cost_usd": round(r.cost_usd, 6),
                "oracle_output": r.oracle_output,
                "error": r.error,
            }
            for r in results
        ]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path
