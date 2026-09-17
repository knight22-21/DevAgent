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
        table.add_column("Missing Files", style="yellow", max_width=28)
        table.add_column("Error / Output", style="dim", max_width=36)

        for r in results:
            status = "[green]ok[/green]" if r.passed else "[red]FAIL[/red]"
            detail = r.error or r.oracle_output or ""
            missed = ", ".join(r.files_missed) if r.files_missed else "-"
            table.add_row(
                r.task_id,
                status,
                str(r.iterations_used) if r.iterations_used else "-",
                f"{r.cost_usd:.4f}" if r.cost_usd else "-",
                f"{r.duration_sec:.1f}",
                missed[:28],
                detail[:60],
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
        tasks_with_misses = sum(1 for r in results if r.files_missed)
        miss_note = (
            f" | [yellow]{tasks_with_misses} task(s) missed expected files[/yellow]"
            if tasks_with_misses else ""
        )
        console.print(
            f"\n[bold]Summary:[/bold] "
            f"[{color}]{passed}/{total} passed ({rate:.0f}%)[/{color}] | "
            f"avg cost ${avg_cost:.4f} | "
            f"avg time {avg_time:.1f}s | "
            f"avg iterations {avg_iter:.1f}"
            f"{miss_note}"
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
    def _result_to_dict(r: TaskResult) -> dict:
        return {
            "task_id": r.task_id,
            "passed": r.passed,
            "duration_sec": round(r.duration_sec, 2),
            "iterations_used": r.iterations_used,
            "cost_usd": round(r.cost_usd, 6),
            "oracle_output": r.oracle_output,
            "error": r.error,
            "files_touched": r.files_touched,
            "files_missed": r.files_missed,
        }

    @staticmethod
    def partial_json_path(label: str = "bench") -> Path:
        """Path for the rolling partial-results file written after each task."""
        return _RESULTS_DIR / f"{label}_partial.json"

    @staticmethod
    def write_partial_json(results: list[TaskResult], path: Path) -> None:
        """Overwrite the partial-results file with current completed tasks."""
        data = [BenchReport._result_to_dict(r) for r in results]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def save_json(results: list[TaskResult], label: str = "bench") -> Path:
        """Save results to benchmarks/results/<label>_<timestamp>.json."""
        import datetime

        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d_%H%M%S")
        path = _RESULTS_DIR / f"{label}_{ts}.json"
        data = [BenchReport._result_to_dict(r) for r in results]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def render_history(limit: int | None = 10) -> None:
        """Print a trend table comparing saved benchmark runs.

        Reads all native_*.json and sweep_*.json files from benchmarks/results/,
        parses the timestamp from the filename, and shows pass rate, avg cost,
        avg iterations, and avg time per run — most recent first.
        """
        import re

        from rich.console import Console
        from rich.table import Table

        console = Console()

        if not _RESULTS_DIR.exists():
            console.print("[yellow]No results directory found — run a benchmark first.[/yellow]")
            return

        # Collect result files (exclude partials)
        pattern = re.compile(r"^(native|sweep|canary)_(\d{8}_\d{6})\.json$")
        runs: list[tuple[str, str, list[dict]]] = []  # (label, ts_str, rows)
        for path in _RESULTS_DIR.iterdir():
            m = pattern.match(path.name)
            if not m:
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(rows, list) or not rows:
                    continue
                runs.append((m.group(1), m.group(2), rows))
            except Exception:  # noqa: S112
                continue

        if not runs:
            console.print("[yellow]No completed result files found in benchmarks/results/.[/yellow]")
            return

        # Sort most-recent first, then apply limit
        runs.sort(key=lambda r: r[1], reverse=True)
        if limit is not None:
            runs = runs[:limit]

        table = Table(title="Benchmark History (most recent first)", border_style="cyan")
        table.add_column("Run", style="cyan", no_wrap=True)
        table.add_column("Date", no_wrap=True)
        table.add_column("Pass Rate", justify="right")
        table.add_column("Passed", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Avg Cost $", justify="right")
        table.add_column("Avg Iter", justify="right")
        table.add_column("Avg Time (s)", justify="right")

        for label, ts_str, rows in runs:
            date_fmt = f"{ts_str[:4]}-{ts_str[4:6]}-{ts_str[6:8]} {ts_str[9:11]}:{ts_str[11:13]}"
            passed = sum(1 for r in rows if r.get("passed"))
            total = len(rows)
            rate = passed / total * 100 if total else 0
            avg_cost = sum(r.get("cost_usd", 0) for r in rows) / total if total else 0
            avg_iter = sum(r.get("iterations_used", 0) for r in rows) / total if total else 0
            avg_time = sum(r.get("duration_sec", 0) for r in rows) / total if total else 0
            color = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
            table.add_row(
                label,
                date_fmt,
                f"[{color}]{rate:.0f}%[/{color}]",
                str(passed),
                str(total),
                f"{avg_cost:.4f}" if avg_cost else "-",
                f"{avg_iter:.1f}" if avg_iter else "-",
                f"{avg_time:.1f}" if avg_time else "-",
            )

        console.print(table)
