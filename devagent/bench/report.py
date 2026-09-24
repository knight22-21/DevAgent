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
    def save_json(
        results: list[TaskResult],
        label: str = "bench",
        model: str | None = None,
        provider: str | None = None,
    ) -> Path:
        """Save results to benchmarks/results/<label>_<timestamp>.json.

        Wraps results in a dict with a meta block so the leaderboard can
        group runs by model without relying on filename conventions.
        """
        import datetime

        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d_%H%M%S")
        path = _RESULTS_DIR / f"{label}_{ts}.json"
        data: dict | list
        if model or provider:
            data = {
                "meta": {
                    "model": model or "unknown",
                    "provider": provider or "unknown",
                    "timestamp": ts,
                },
                "results": [BenchReport._result_to_dict(r) for r in results],
            }
        else:
            data = [BenchReport._result_to_dict(r) for r in results]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _load_run_file(path: Path) -> tuple[dict | None, list[dict]]:
        """Read a result JSON; return (meta_or_None, rows)."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None, []
        if isinstance(raw, dict) and "results" in raw:
            return raw.get("meta"), raw["results"]
        if isinstance(raw, list) and raw:
            return None, raw
        return None, []

    @staticmethod
    def render_history(limit: int | None = 10, src_dir: Path | None = None) -> None:
        """Print a trend table comparing saved benchmark runs.

        Reads all native_*.json, sweep_*.json, and canary_*.json files from
        benchmarks/results/ (or src_dir if provided), parses the timestamp from the
        filename, and shows pass rate, avg cost, avg iterations, and avg time per
        run — most recent first.
        """
        import re

        from rich.console import Console
        from rich.table import Table

        console = Console()

        results_dir = src_dir if src_dir is not None else _RESULTS_DIR
        if not results_dir.exists():
            console.print("[yellow]No results directory found — run a benchmark first.[/yellow]")
            return

        # Collect result files (exclude partials)
        pattern = re.compile(r"^(native|sweep|canary)_(\d{8}_\d{6})\.json$")
        runs: list[tuple[str, str, dict | None, list[dict]]] = []
        for path in results_dir.iterdir():
            m = pattern.match(path.name)
            if not m:
                continue
            meta, rows = BenchReport._load_run_file(path)
            if not rows:
                continue
            runs.append((m.group(1), m.group(2), meta, rows))

        if not runs:
            console.print("[yellow]No completed result files found in benchmarks/results/.[/yellow]")
            return

        # Sort most-recent first, then apply limit
        runs.sort(key=lambda r: r[1], reverse=True)
        if limit is not None:
            runs = runs[:limit]

        table = Table(title="Benchmark History (most recent first)", border_style="cyan")
        table.add_column("Run", style="cyan", no_wrap=True)
        table.add_column("Model", style="dim", no_wrap=True)
        table.add_column("Date", no_wrap=True)
        table.add_column("Pass Rate", justify="right")
        table.add_column("Passed", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Avg Cost $", justify="right")
        table.add_column("Avg Iter", justify="right")
        table.add_column("Avg Time (s)", justify="right")

        for label, ts_str, meta, rows in runs:
            date_fmt = f"{ts_str[:4]}-{ts_str[4:6]}-{ts_str[6:8]} {ts_str[9:11]}:{ts_str[11:13]}"
            model_label = meta["model"] if meta else "—"
            passed = sum(1 for r in rows if r.get("passed"))
            total = len(rows)
            rate = passed / total * 100 if total else 0
            avg_cost = sum(r.get("cost_usd", 0) for r in rows) / total if total else 0
            avg_iter = sum(r.get("iterations_used", 0) for r in rows) / total if total else 0
            avg_time = sum(r.get("duration_sec", 0) for r in rows) / total if total else 0
            color = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
            table.add_row(
                label,
                model_label,
                date_fmt,
                f"[{color}]{rate:.0f}%[/{color}]",
                str(passed),
                str(total),
                f"{avg_cost:.4f}" if avg_cost else "-",
                f"{avg_iter:.1f}" if avg_iter else "-",
                f"{avg_time:.1f}" if avg_time else "-",
            )

        console.print(table)

    @staticmethod
    def render_leaderboard(src_dir: Path | None = None) -> None:
        """Print a leaderboard table grouped by model (best score per model)."""
        import re

        from rich.console import Console
        from rich.table import Table

        console = Console()
        results_dir = src_dir if src_dir is not None else _RESULTS_DIR
        if not results_dir.exists():
            console.print("[yellow]No results directory found.[/yellow]")
            return

        pattern = re.compile(r"^native_(\d{8}_\d{6})\.json$")
        entries: list[tuple[str, str, str, dict | None, list[dict]]] = []

        for path in results_dir.iterdir():
            m = pattern.match(path.name)
            if not m:
                continue
            meta, rows = BenchReport._load_run_file(path)
            if not rows:
                continue
            ts = m.group(1)
            model = meta["model"] if meta else "unknown"
            provider = meta["provider"] if meta else "unknown"
            entries.append((ts, model, provider, meta, rows))

        if not entries:
            console.print("[yellow]No native result files found.[/yellow]")
            return

        # Group by (model, provider) — keep best score + latest run date
        groups: dict[tuple[str, str], dict] = {}
        for ts, model, provider, meta, rows in entries:
            key = (model, provider)
            passed = sum(1 for r in rows if r.get("passed"))
            total = len(rows)
            rate = passed / total if total else 0
            avg_time = sum(r.get("duration_sec", 0) for r in rows) / total if total else 0
            date_fmt = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            if key not in groups:
                groups[key] = {
                    "best_passed": passed, "best_total": total, "best_rate": rate,
                    "latest_passed": passed, "latest_total": total, "latest_date": date_fmt,
                    "avg_time": avg_time, "runs": 1,
                }
            else:
                g = groups[key]
                g["runs"] += 1
                if rate > g["best_rate"]:
                    g["best_passed"] = passed
                    g["best_total"] = total
                    g["best_rate"] = rate
                if ts > g["latest_date"].replace("-", ""):
                    g["latest_passed"] = passed
                    g["latest_total"] = total
                    g["latest_date"] = date_fmt
                    g["avg_time"] = avg_time

        # Sort by best score descending
        ranked = sorted(groups.items(), key=lambda x: x[1]["best_rate"], reverse=True)

        table = Table(title="DevAgent Leaderboard", border_style="cyan", show_lines=True)
        table.add_column("Rank", justify="right", style="bold")
        table.add_column("Model", style="cyan")
        table.add_column("Provider")
        table.add_column("Best Score", justify="right")
        table.add_column("Latest Score", justify="right")
        table.add_column("Latest Date", no_wrap=True)
        table.add_column("Runs", justify="right")
        table.add_column("Avg Time", justify="right")

        for rank, ((model, provider), g) in enumerate(ranked, 1):
            best_pct = g["best_rate"] * 100
            latest_pct = g["latest_passed"] / g["latest_total"] * 100 if g["latest_total"] else 0
            color = "green" if best_pct >= 80 else "yellow" if best_pct >= 50 else "red"
            table.add_row(
                str(rank),
                model,
                provider,
                f"[{color}]{g['best_passed']}/{g['best_total']} ({best_pct:.0f}%)[/{color}]",
                f"{g['latest_passed']}/{g['latest_total']} ({latest_pct:.0f}%)",
                g["latest_date"],
                str(g["runs"]),
                f"{g['avg_time']:.1f}s",
            )

        console.print(table)

    @staticmethod
    def generate_leaderboard_md(src_dir: Path | None = None, date: str = "") -> str:
        """Return a markdown string for LEADERBOARD.md, grouped by model."""
        import re

        results_dir = src_dir if src_dir is not None else _RESULTS_DIR
        pattern = re.compile(r"^native_(\d{8}_\d{6})\.json$")
        entries: list[tuple[str, str, str, list[dict]]] = []

        if results_dir.exists():
            for path in results_dir.iterdir():
                m = pattern.match(path.name)
                if not m:
                    continue
                meta, rows = BenchReport._load_run_file(path)
                if not rows:
                    continue
                ts = m.group(1)
                model = meta["model"] if meta else "unknown"
                provider = meta["provider"] if meta else "unknown"
                entries.append((ts, model, provider, rows))

        groups: dict[tuple[str, str], dict] = {}
        for ts, model, provider, rows in entries:
            key = (model, provider)
            passed = sum(1 for r in rows if r.get("passed"))
            total = len(rows)
            rate = passed / total if total else 0
            avg_time = sum(r.get("duration_sec", 0) for r in rows) / total if total else 0
            date_fmt = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            if key not in groups or rate > groups[key]["best_rate"]:
                existing_runs = groups[key]["runs"] if key in groups else 0
                groups[key] = {
                    "best_passed": passed, "best_total": total, "best_rate": rate,
                    "latest_passed": passed, "latest_total": total,
                    "latest_date": date_fmt, "avg_time": avg_time,
                    "runs": existing_runs + 1,
                }
            else:
                groups[key]["runs"] += 1
                if ts > groups[key]["latest_date"].replace("-", ""):
                    groups[key]["latest_passed"] = passed
                    groups[key]["latest_total"] = total
                    groups[key]["latest_date"] = date_fmt
                    groups[key]["avg_time"] = avg_time

        ranked = sorted(groups.items(), key=lambda x: x[1]["best_rate"], reverse=True)

        updated = date or "auto-generated"
        lines = [
            "# DevAgent Leaderboard",
            "",
            f"_Last updated: {updated}_",
            "",
            "Scores are from `devagent bench native --live` runs against the full task set.",
            "Pass = oracle exits 0 after the agent loop. Higher is better.",
            "",
            "| Rank | Model | Provider | Best Score | Latest Score | Latest Run | Runs | Avg Time |",
            "|------|-------|----------|------------|--------------|------------|------|----------|",
        ]

        for rank, ((model, provider), g) in enumerate(ranked, 1):
            best_pct = g["best_rate"] * 100
            latest_pct = g["latest_passed"] / g["latest_total"] * 100 if g["latest_total"] else 0
            lines.append(
                f"| {rank} | `{model}` | {provider} "
                f"| **{g['best_passed']}/{g['best_total']} ({best_pct:.0f}%)** "
                f"| {g['latest_passed']}/{g['latest_total']} ({latest_pct:.0f}%) "
                f"| {g['latest_date']} | {g['runs']} | {g['avg_time']:.1f}s |"
            )

        if not ranked:
            lines.append("| — | No live results yet | — | — | — | — | — | — |")

        lines += [
            "",
            "---",
            "",
            "To add your model to this leaderboard:",
            "",
            "```bash",
            "devagent bench native --live --model <your-model> --provider <ollama|anthropic|openai>",
            "```",
            "",
            "Results are saved automatically to `benchmarks/results/` and picked up next time",
            "`devagent bench leaderboard` runs.",
        ]

        return "\n".join(lines) + "\n"
