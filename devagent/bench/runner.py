"""BenchRunner — loads tasks and executes them against a fixture project copy."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from devagent.bench.oracle import OracleEvaluator

_console = Console()

_TASKS_DIR = Path(__file__).parent.parent.parent / "benchmarks" / "tasks"
_FIXTURES_DIR = Path(__file__).parent.parent.parent / "benchmarks" / "fixtures"


@dataclass
class Task:
    id: str
    category: str
    difficulty: str
    description: str
    fixture_project: str
    oracle_check: str
    oracle_pass_exit_code: int = 0
    expected_files_touched: list[str] = field(default_factory=list)
    max_iterations: int = 30
    timeout_sec: int = 300
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        return cls(
            id=data["id"],
            category=data["category"],
            difficulty=data["difficulty"],
            description=data["description"],
            fixture_project=data["fixture_project"],
            oracle_check=data["oracle_check"],
            oracle_pass_exit_code=data.get("oracle_pass_exit_code", 0),
            expected_files_touched=data.get("expected_files_touched", []),
            max_iterations=data.get("max_iterations", 30),
            timeout_sec=data.get("timeout_sec", 300),
            tags=data.get("tags", []),
        )


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    duration_sec: float
    iterations_used: int = 0
    cost_usd: float = 0.0
    oracle_output: str = ""
    error: str = ""


class BenchRunner:
    """Loads tasks from task_set.json and executes them.

    In dry_run mode (the default), the runner copies the fixture project to a
    temp dir and runs the oracle WITHOUT invoking the agent.  This lets the CI
    canary verify the oracle/framework infrastructure without a real LLM.

    Pass dry_run=False to run the actual DevAgent loop against each task.
    """

    def __init__(
        self,
        tasks: list[Task] | None = None,
        dry_run: bool = True,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> None:
        self.tasks = tasks or self.load_tasks()
        self.dry_run = dry_run
        self.model = model
        self.max_iterations = max_iterations
        self._oracle = OracleEvaluator()

    # ------------------------------------------------------------------
    # Class helpers
    # ------------------------------------------------------------------

    @staticmethod
    def load_tasks(
        task_file: str | Path | None = None,
        category: str | None = None,
        difficulty: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Task]:
        """Load tasks from task_set.json with optional filtering."""
        path = Path(task_file) if task_file else _TASKS_DIR / "task_set.json"
        raw: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        tasks = [Task.from_dict(d) for d in raw]
        if category:
            tasks = [t for t in tasks if t.category == category]
        if difficulty:
            tasks = [t for t in tasks if t.difficulty == difficulty]
        if tags:
            tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]
        return tasks

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_all(self) -> list[TaskResult]:
        return [self.run_task(t) for t in self.tasks]

    def run_task(self, task: Task) -> TaskResult:
        """Execute a single task and return its result."""
        fixture_src = _FIXTURES_DIR / task.fixture_project
        if not fixture_src.is_dir():
            return TaskResult(
                task_id=task.id,
                passed=False,
                duration_sec=0.0,
                error=f"fixture_project not found: {fixture_src}",
            )

        if not self.dry_run:
            _console.print(
                f"  [cyan]▶[/cyan] [dim]{task.id}[/dim]  {task.description[:72].rstrip()}…"
            )

        with tempfile.TemporaryDirectory(prefix="devagent_bench_") as tmp:
            work_dir = Path(tmp) / task.fixture_project
            shutil.copytree(
                fixture_src,
                work_dir,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

            start = time.monotonic()
            try:
                if self.dry_run:
                    result = self._run_dry(task, work_dir)
                else:
                    result = self._run_live(task, work_dir)
            except Exception as exc:
                result = TaskResult(
                    task_id=task.id,
                    passed=False,
                    duration_sec=time.monotonic() - start,
                    error=str(exc),
                )

            result.duration_sec = time.monotonic() - start
            return result

    def _run_dry(self, task: Task, work_dir: Path) -> TaskResult:
        """Dry run — just evaluate the oracle on the unmodified fixture."""
        passed, output = self._oracle.evaluate_verbose(
            task.oracle_check,
            cwd=str(work_dir),
            pass_exit_code=task.oracle_pass_exit_code,
            timeout=task.timeout_sec,
        )
        return TaskResult(
            task_id=task.id,
            passed=passed,
            duration_sec=0.0,
            oracle_output=output[:500],
        )

    def _run_live(self, task: Task, work_dir: Path) -> TaskResult:
        """Live run — invoke the DevAgent loop, then evaluate the oracle."""
        from devagent.agent.flows import DevAgentSession
        from devagent.core.config import load_config

        cfg = load_config()
        if self.model:
            cfg.llm.model = self.model
        # Task limit takes effect via cfg; runner-level override takes precedence.
        cfg.agent.max_iterations = self.max_iterations or task.max_iterations

        try:
            session = DevAgentSession(
                project_root=str(work_dir),
                cfg=cfg,
                bare=True,  # no DEVAGENT.md / CodePrism — clean bench env
            )
            session.run_message(task.description, quiet=True)
        except Exception as exc:
            return TaskResult(
                task_id=task.id,
                passed=False,
                duration_sec=0.0,
                error=str(exc),
            )

        cost = session._budget.total_cost_usd
        iterations = sum(
            row.get("calls", 0) for row in session._budget.per_model_summary()
        )

        passed, output = self._oracle.evaluate_verbose(
            task.oracle_check,
            cwd=str(work_dir),
            pass_exit_code=task.oracle_pass_exit_code,
            timeout=task.timeout_sec,
        )
        return TaskResult(
            task_id=task.id,
            passed=passed,
            duration_sec=0.0,
            iterations_used=iterations,
            cost_usd=cost,
            oracle_output=output[:500],
        )
