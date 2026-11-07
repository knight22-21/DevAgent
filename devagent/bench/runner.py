"""BenchRunner — loads tasks and executes them against a fixture project copy."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from devagent.bench.oracle import OracleEvaluator

_console = Console()

_TASKS_DIR = Path(__file__).parent.parent.parent / "benchmarks" / "tasks"

# Tools exposed to the model during benchmarks — write_file is preferred over
# edit_file for small models; exact-string matching in edit_file is too fragile.
_BENCH_TOOLS = ["read_file", "write_file", "list_files", "grep", "run_shell"]

# Minimal system prompt for bench mode — replaces the verbose DevAgent base prompt.
# Smaller models (7B range) struggle with verbose prompts and fall back to text plans;
# this terse version keeps them in tool-call mode.
_BENCH_SYSTEM_PROMPT = (
    "You are a coding assistant. Complete every task by calling tools — never answer in plain text. "
    "Read the full target file and the relevant tests before editing. Preserve every existing public function, "
    "import, export, and behavior unless the task explicitly asks for a change. "
    "For bug fixes and features, write the COMPLETE corrected file, then run the exact oracle command. "
    "For a new feature, implement the named API and add the requested named test; a test command that says "
    "\\\"deselected\\\" or has collection/import errors is a failure, so keep iterating until it runs the intended tests. "
    "For JavaScript or Go tasks, write the complete target source file and run the exact node/go oracle. "
    "For explain, review, audit, or onboarding tasks, read all requested files, then call write_file to save "
    "the answer to the exact required path (usually DEVAGENT_OUTPUT.txt or DEVAGENT.md). After writing, call "
    "read_file on that path to verify it exists and contains the requested details; never rely on final text. "
    "Be technical and specific — name exact functions, vulnerability types, severities, and code patterns."
)
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
    dry_run_patches: dict[str, str] = field(default_factory=dict)

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
            dry_run_patches=data.get("dry_run_patches", {}),
        )


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    duration_sec: float
    iterations_used: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    oracle_output: str = ""
    error: str = ""
    files_touched: list[str] = field(default_factory=list)
    files_missed: list[str] = field(default_factory=list)
    failure_class: str = "passed"
    diagnostics: dict[str, object] = field(default_factory=dict)


def _snapshot_mtimes(root: Path) -> dict[str, float]:
    """Return {relative_posix_path: mtime} for every file under root."""
    result: dict[str, float] = {}
    for p in root.rglob("*"):
        if p.is_file():
            result[p.relative_to(root).as_posix()] = p.stat().st_mtime
    return result


def _changed_files(before: dict[str, float], after: dict[str, float]) -> list[str]:
    """Return sorted list of paths that were added or modified between snapshots."""
    return sorted(
        path for path, mtime in after.items()
        if path not in before or before[path] != mtime
    )


def _classify_failure(
    *,
    passed: bool,
    error: str,
    oracle_output: str,
    files_missed: list[str],
    tool_trace: list[dict[str, object]],
) -> str:
    """Classify the first observable failure boundary for a live task."""
    if passed:
        return "passed"
    if "timed out" in error.lower() or "timeout" in error.lower():
        return "timeout_budget"
    if any(event.get("ok") is False for event in tool_trace):
        return "tool_call_schema"
    if files_missed:
        return "incomplete_file_writing"
    output = oracle_output.lower()
    if any(marker in output for marker in ("pytest", "assert", "traceback", "error", "fail", "deselected")):
        return "test_repair_failure"
    return "model_reasoning_failure"


def _summarize_tool_args(tool_name: str, args: object) -> dict[str, object]:
    """Capture safe, compact tool evidence without persisting file contents."""
    if not isinstance(args, dict):
        return {"type": type(args).__name__}
    summary: dict[str, object] = {"keys": sorted(str(k) for k in args)}
    if "path" in args:
        summary["path"] = str(args["path"])
    if "content" in args:
        content = args["content"]
        summary["content_chars"] = len(content) if isinstance(content, str) else 0
    if tool_name == "run_shell" and "command" in args:
        summary["command"] = str(args["command"])[:240]
    return summary


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
        provider: str | None = None,
        max_iterations: int | None = None,
        effort: str | None = None,
    ) -> None:
        self.tasks = tasks or self.load_tasks()
        self.dry_run = dry_run
        self.model = model
        self.provider = provider
        self.max_iterations = max_iterations
        self.effort = effort
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

    def run_all(
        self,
        on_result: Callable[[TaskResult, list[TaskResult]], None] | None = None,
    ) -> list[TaskResult]:
        results: list[TaskResult] = []
        for task in self.tasks:
            r = self.run_task(task)
            results.append(r)
            if on_result:
                on_result(r, results)
        return results

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
                f"  [cyan]>>[/cyan] [dim]{task.id}[/dim]  {task.description[:72].rstrip()}"
            )

        tmp = tempfile.mkdtemp(prefix="devagent_bench_")
        try:
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
        finally:
            shutil.rmtree(tmp, ignore_errors=True)  # ignore_errors avoids Windows file-lock crash

    def _run_dry(self, task: Task, work_dir: Path) -> TaskResult:
        """Dry run — apply the task's known patch, then evaluate its oracle."""
        for relative_path, content in task.dry_run_patches.items():
            target = work_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
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
            failure_class=_classify_failure(
                passed=passed,
                error="",
                oracle_output=output,
                files_missed=[],
                tool_trace=[],
            ),
        )

    def _run_live(self, task: Task, work_dir: Path) -> TaskResult:
        """Live run — invoke the DevAgent loop, then evaluate the oracle."""
        from devagent.agent.flows import DevAgentSession
        from devagent.core.config import RouterConfig, load_config

        cfg = load_config()
        if self.provider:
            cfg.llm.provider = self.provider
        if self.model:
            cfg.llm.model = self.model
        if self.effort:
            cfg.llm.effort = self.effort
        # Task limit takes effect via cfg; runner-level override takes precedence.
        cfg.agent.max_iterations = self.max_iterations or task.max_iterations

        # When the bench specifies a model/provider, pin ALL routing tiers to it
        # so the multi-model router doesn't pull in an uninstalled model.
        if self.provider or self.model:
            route = {"provider": cfg.llm.provider, "model": cfg.llm.model}
            cfg.router = RouterConfig(
                planning=route,
                coding=route,
                reviewing=route,
                cheap=route,
                fallback=route,
            )

        tool_trace: list[dict[str, object]] = []
        try:
            session = DevAgentSession(
                project_root=str(work_dir),
                cfg=cfg,
                bare=True,  # no DEVAGENT.md / CodePrism — clean bench env
                system_prompt_override=_BENCH_SYSTEM_PROMPT,
            )
            # Restrict the tool schema sent to the model — smaller models get
            # overwhelmed by 20+ tools and fall back to writing text plans.
            restricted = session._loop.registry.get_restricted_definitions(_BENCH_TOOLS)
            session._loop.registry.get_definitions = lambda _r=restricted: _r  # type: ignore[method-assign]

            tool_calls = 0
            for tool_name in _BENCH_TOOLS:
                original_handler = session._loop.registry._handlers.get(tool_name)
                if original_handler is None:
                    continue

                def _counted_handler(args, _handler=original_handler, _tool_name=tool_name):
                    nonlocal tool_calls
                    tool_calls += 1
                    event: dict[str, object] = {
                        "tool": _tool_name,
                        "args": _summarize_tool_args(_tool_name, args),
                    }
                    try:
                        result = _handler(args)
                        event["ok"] = True
                        if isinstance(result, str):
                            event["result_chars"] = len(result)
                            event["result_tail"] = result[-240:]
                        return result
                    except Exception as exc:
                        event["ok"] = False
                        event["error"] = str(exc)[:240]
                        raise
                    finally:
                        tool_trace.append(event)

                session._loop.registry._handlers[tool_name] = _counted_handler

            # Wrap write_file to auto-syntax-check .py files and surface errors
            # to the model so it can self-correct before proceeding.
            _orig_write = session._loop.registry._handlers["write_file"]

            def _write_with_syntax_check(args: dict) -> str:
                result = _orig_write(args)
                path = args.get("path", "")
                if path.endswith(".py"):
                    full = work_dir / path
                    if full.exists():
                        chk = subprocess.run(
                            ["python", "-m", "py_compile", str(full)],
                            capture_output=True,
                            text=True,
                        )
                        if chk.returncode != 0:
                            result += f"\n[syntax error] {chk.stderr.strip()}"
                return result

            session._loop.registry._handlers["write_file"] = _write_with_syntax_check

            # Snapshot file mtimes so we can tell which files the agent touched
            snapshot_before = _snapshot_mtimes(work_dir)

            wall_timeout = task.timeout_sec or 120
            thread_exc: list[Exception] = []
            final_answer: list[str] = []

            def _run() -> None:
                try:
                    answer = session.run_message(task.description, quiet=True)
                    if answer:
                        final_answer.append(answer)
                except Exception as exc:
                    thread_exc.append(exc)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=wall_timeout)

            if t.is_alive():
                return TaskResult(
                    task_id=task.id,
                    passed=False,
                    duration_sec=0.0,
                    error=f"agent timed out after {wall_timeout}s",
                    failure_class="timeout_budget",
                    diagnostics={"tool_trace": tool_trace, "timeout_sec": wall_timeout},
                )
            if thread_exc:
                raise thread_exc[0]

        except Exception as exc:
            return TaskResult(
                task_id=task.id,
                passed=False,
                duration_sec=0.0,
                error=str(exc),
                failure_class="tool_call_schema" if tool_trace else "model_reasoning_failure",
                diagnostics={"tool_trace": tool_trace},
            )

        cost = session._budget.total_cost_usd
        iterations = session._budget.call_count

        # Compute which files were touched vs. what the task expected
        snapshot_after = _snapshot_mtimes(work_dir)
        touched = _changed_files(snapshot_before, snapshot_after)
        expected = [p.replace("\\", "/") for p in task.expected_files_touched]
        # A file counts as "covered" if any touched path ends with the expected path
        missed = [p for p in expected if not any(t.endswith(p) for t in touched)]

        passed, output = self._oracle.evaluate_verbose(
            task.oracle_check,
            cwd=str(work_dir),
            pass_exit_code=task.oracle_pass_exit_code,
            timeout=task.timeout_sec,
        )
        failure_class = _classify_failure(
            passed=passed,
            error="",
            oracle_output=output,
            files_missed=missed,
            tool_trace=tool_trace,
        )
        return TaskResult(
            task_id=task.id,
            passed=passed,
            duration_sec=0.0,
            iterations_used=iterations,
            llm_calls=iterations,
            tool_calls=tool_calls,
            cost_usd=cost,
            oracle_output=output[:500],
            files_touched=touched,
            files_missed=missed,
            failure_class=failure_class,
            diagnostics={
                "tool_trace": tool_trace,
                "write_targets": [
                    event["args"].get("path")
                    for event in tool_trace
                    if event.get("tool") == "write_file"
                    and isinstance(event.get("args"), dict)
                ],
                "oracle_ran": True,
            },
        )
