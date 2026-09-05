"""SweepRunner — run the native task set across a parameter grid (B4)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from devagent.bench.runner import BenchRunner, TaskResult

console = Console()


@dataclass
class SweepResult:
    params: dict
    results: list[TaskResult]

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def avg_cost_usd(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.cost_usd for r in self.results) / len(self.results)

    @property
    def avg_duration_sec(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.duration_sec for r in self.results) / len(self.results)


_DEFAULT_GRID: dict[str, list] = {
    "model": ["qwen2.5-coder:7b", "qwen2.5-coder:14b"],
    "max_iterations": [10, 30],
}


class SweepRunner:
    """Runs BenchRunner over a parameter grid and reports cost-vs-correctness."""

    def __init__(
        self,
        param_grid: dict[str, list] | None = None,
        task_limit: int | None = None,
        category: str | None = None,
        difficulty: str | None = None,
        dry_run: bool = False,
        provider: str | None = None,
    ) -> None:
        self.param_grid = param_grid or _DEFAULT_GRID
        self.task_limit = task_limit
        self.category = category
        self.difficulty = difficulty
        self.dry_run = dry_run
        self.provider = provider

    def run(self) -> list[SweepResult]:
        """Execute all parameter combinations and return sweep results."""
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        combos = list(itertools.product(*values))

        tasks = BenchRunner.load_tasks(
            category=self.category,
            difficulty=self.difficulty,
        )
        if self.task_limit:
            tasks = tasks[: self.task_limit]

        sweep_results: list[SweepResult] = []

        for combo in combos:
            params = dict(zip(keys, combo))
            console.print(f"\n[bold cyan]Sweep:[/bold cyan] {params}")

            runner = BenchRunner(
                tasks=tasks,
                dry_run=self.dry_run,
                provider=self.provider,
                model=params.get("model"),
                max_iterations=params.get("max_iterations"),
            )
            results = runner.run_all()
            sweep_results.append(SweepResult(params=params, results=results))

        return sweep_results

    @staticmethod
    def render_table(sweep_results: list[SweepResult], param_keys: list[str]) -> None:
        """Render a comparison table of all sweep combinations."""
        table = Table(title="Cost-vs-Correctness Sweep", show_lines=True)

        for k in param_keys:
            table.add_column(k, style="cyan")
        table.add_column("Pass Rate", justify="right")
        table.add_column("Avg Cost $", justify="right")
        table.add_column("Avg Time (s)", justify="right")

        for sr in sweep_results:
            rate = sr.pass_rate * 100
            color = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
            row = [str(sr.params.get(k, "-")) for k in param_keys]
            row += [
                f"[{color}]{rate:.0f}%[/{color}]",
                f"{sr.avg_cost_usd:.4f}",
                f"{sr.avg_duration_sec:.1f}",
            ]
            table.add_row(*row)

        console.print(table)
