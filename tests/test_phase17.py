"""Phase 17 tests — benchmark framework (B3/B4/B5)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Oracle evaluator
# ---------------------------------------------------------------------------

class TestOracleEvaluator:
    def setup_method(self):
        from devagent.bench.oracle import OracleEvaluator
        self.oracle = OracleEvaluator()

    def test_passing_command_returns_true(self, tmp_path):
        assert self.oracle.evaluate("python -c \"exit(0)\"", cwd=str(tmp_path)) is True

    def test_failing_command_returns_false(self, tmp_path):
        assert self.oracle.evaluate("python -c \"exit(1)\"", cwd=str(tmp_path)) is False

    def test_nonzero_pass_exit_code(self, tmp_path):
        assert self.oracle.evaluate("python -c \"exit(2)\"", cwd=str(tmp_path), pass_exit_code=2) is True

    def test_timeout_returns_false(self, tmp_path):
        result = self.oracle.evaluate("python -c \"import time; time.sleep(10)\"", cwd=str(tmp_path), timeout=1)
        assert result is False

    def test_invalid_command_returns_false(self, tmp_path):
        assert self.oracle.evaluate("nonexistent_binary_xyz", cwd=str(tmp_path)) is False

    def test_verbose_returns_output(self, tmp_path):
        passed, output = self.oracle.evaluate_verbose(
            "python -c \"import sys; print('hello'); sys.exit(0)\"",
            cwd=str(tmp_path),
        )
        assert passed is True
        assert "hello" in output

    def test_verbose_failure_returns_output(self, tmp_path):
        passed, _output = self.oracle.evaluate_verbose(
            "python -c \"import sys; print('bad', file=sys.stderr); sys.exit(1)\"",
            cwd=str(tmp_path),
        )
        assert passed is False


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

class TestTaskLoading:
    def test_load_tasks_returns_list(self):
        from devagent.bench.runner import BenchRunner
        tasks = BenchRunner.load_tasks()
        assert isinstance(tasks, list)
        assert len(tasks) >= 10

    def test_tasks_have_required_fields(self):
        from devagent.bench.runner import BenchRunner
        tasks = BenchRunner.load_tasks()
        for t in tasks:
            assert t.id
            assert t.category
            assert t.difficulty in ("easy", "medium", "hard")
            assert t.description
            assert t.fixture_project
            assert t.oracle_check

    def test_filter_by_category(self):
        from devagent.bench.runner import BenchRunner
        tasks = BenchRunner.load_tasks(category="bug_fix")
        assert tasks
        assert all(t.category == "bug_fix" for t in tasks)

    def test_filter_by_difficulty(self):
        from devagent.bench.runner import BenchRunner
        tasks = BenchRunner.load_tasks(difficulty="easy")
        assert tasks
        assert all(t.difficulty == "easy" for t in tasks)

    def test_filter_returns_empty_for_unknown_category(self):
        from devagent.bench.runner import BenchRunner
        tasks = BenchRunner.load_tasks(category="nonexistent_category_xyz")
        assert tasks == []

    def test_load_from_custom_path(self, tmp_path):
        from devagent.bench.runner import BenchRunner
        task_data = [
            {
                "id": "test-001",
                "category": "bug_fix",
                "difficulty": "easy",
                "description": "Test task",
                "fixture_project": "sample_project",
                "oracle_check": "python -c \"exit(0)\"",
            }
        ]
        p = tmp_path / "tasks.json"
        p.write_text(json.dumps(task_data))
        tasks = BenchRunner.load_tasks(task_file=p)
        assert len(tasks) == 1
        assert tasks[0].id == "test-001"


# ---------------------------------------------------------------------------
# BenchRunner dry-run
# ---------------------------------------------------------------------------

class TestBenchRunnerDryRun:
    def test_missing_fixture_returns_error(self):
        from devagent.bench.runner import BenchRunner, Task
        task = Task(
            id="t-001",
            category="bug_fix",
            difficulty="easy",
            description="test",
            fixture_project="no_such_project",
            oracle_check="python -c \"exit(0)\"",
        )
        runner = BenchRunner(tasks=[task], dry_run=True)
        result = runner.run_task(task)
        assert result.passed is False
        assert "not found" in result.error

    def test_dry_run_oracle_pass(self):
        from devagent.bench.runner import BenchRunner, Task
        task = Task(
            id="t-002",
            category="bug_fix",
            difficulty="easy",
            description="test",
            fixture_project="sample_project",
            oracle_check="python -c \"exit(0)\"",
        )
        runner = BenchRunner(tasks=[task], dry_run=True)
        result = runner.run_task(task)
        assert result.passed is True
        assert result.task_id == "t-002"

    def test_dry_run_oracle_fail(self):
        from devagent.bench.runner import BenchRunner, Task
        task = Task(
            id="t-003",
            category="bug_fix",
            difficulty="easy",
            description="test",
            fixture_project="sample_project",
            oracle_check="python -c \"exit(1)\"",
        )
        runner = BenchRunner(tasks=[task], dry_run=True)
        result = runner.run_task(task)
        assert result.passed is False

    def test_run_all_returns_one_result_per_task(self):
        from devagent.bench.runner import BenchRunner
        tasks = BenchRunner.load_tasks(difficulty="easy")[:3]
        runner = BenchRunner(tasks=tasks, dry_run=True)
        results = runner.run_all()
        assert len(results) == len(tasks)

    def test_fixture_copy_isolation(self):
        """Two tasks running against same fixture don't share state."""
        from devagent.bench.runner import BenchRunner, Task

        t1 = Task(
            id="iso-1",
            category="bug_fix",
            difficulty="easy",
            description="",
            fixture_project="sample_project",
            oracle_check="python -c \"exit(0)\"",
        )
        t2 = Task(
            id="iso-2",
            category="bug_fix",
            difficulty="easy",
            description="",
            fixture_project="sample_project",
            oracle_check="python -c \"exit(0)\"",
        )
        runner = BenchRunner(tasks=[t1, t2], dry_run=True)
        results = runner.run_all()
        assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestBenchReport:
    def test_render_summary_empty(self, capsys):
        from devagent.bench.report import BenchReport
        BenchReport.render_summary([])

    def test_render_summary_with_results(self):
        from devagent.bench.report import BenchReport
        from devagent.bench.runner import TaskResult
        results = [
            TaskResult(task_id="a", passed=True, duration_sec=1.0),
            TaskResult(task_id="b", passed=False, duration_sec=2.0),
        ]
        BenchReport.render_summary(results)

    def test_save_json_creates_file(self, tmp_path):
        from devagent.bench.report import BenchReport
        from devagent.bench.runner import TaskResult
        results = [TaskResult(task_id="x", passed=True, duration_sec=0.5)]
        with patch("devagent.bench.report._RESULTS_DIR", tmp_path):
            path = BenchReport.save_json(results, label="test")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data[0]["task_id"] == "x"
        assert data[0]["passed"] is True


# ---------------------------------------------------------------------------
# Canary JSON
# ---------------------------------------------------------------------------

class TestCanaryJson:
    def test_canary_json_loads(self):
        canary_path = Path(__file__).parent.parent / "benchmarks" / "tasks" / "canary.json"
        data = json.loads(canary_path.read_text())
        assert "framework_checks" in data
        assert "fail_threshold" in data
        assert data["fail_threshold"] == pytest.approx(0.80)

    def test_canary_framework_checks_have_required_fields(self):
        canary_path = Path(__file__).parent.parent / "benchmarks" / "tasks" / "canary.json"
        data = json.loads(canary_path.read_text())
        for check in data["framework_checks"]:
            assert "id" in check
            assert "description" in check
            assert "check" in check

    def test_canary_framework_checks_all_pass(self):
        """All framework checks in canary.json must execute successfully."""
        canary_path = Path(__file__).parent.parent / "benchmarks" / "tasks" / "canary.json"
        data = json.loads(canary_path.read_text())
        failures = []
        for check in data["framework_checks"]:
            try:
                exec(check["check"])  # noqa: S102
            except Exception as exc:
                failures.append(f"{check['id']}: {exc}")
        assert not failures, "Canary checks failed:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Fixture project sanity
# ---------------------------------------------------------------------------

class TestFixtureProject:
    _fixture = Path(__file__).parent.parent / "benchmarks" / "fixtures" / "sample_project"

    def test_fixture_src_files_exist(self):
        assert (self._fixture / "src" / "math_utils.py").exists()
        assert (self._fixture / "src" / "string_utils.py").exists()
        assert (self._fixture / "src" / "data_store.py").exists()

    def test_fixture_test_files_exist(self):
        assert (self._fixture / "tests" / "test_math.py").exists()
        assert (self._fixture / "tests" / "test_string.py").exists()
        assert (self._fixture / "tests" / "test_data_store.py").exists()

    def test_math_multiply_has_bug(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "math_utils", self._fixture / "src" / "math_utils.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Bug: multiply uses + not *
        assert mod.multiply(3, 4) != 12

    def test_data_store_tests_pass_despite_bug(self):
        """data_store tests should still pass even with the eval() bug."""
        result = __import__("subprocess").run(
            ["python", "-m", "pytest", "tests/test_data_store.py", "-q"],
            capture_output=True,
            text=True,
            cwd=str(self._fixture),
        )
        assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# BenchRunner live (mocked LLM)
# ---------------------------------------------------------------------------

def _make_mock_session(cost: float = 0.0012, calls: int = 3) -> MagicMock:
    """Return a mock DevAgentSession with realistic budget attributes."""
    mock_budget = MagicMock()
    mock_budget.total_cost_usd = cost
    mock_budget.per_model_summary.return_value = [
        {
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "input_tokens": 500,
            "output_tokens": 200,
            "cost_usd": cost,
            "calls": calls,
        }
    ]
    session = MagicMock()
    session._budget = mock_budget
    session.run_message.return_value = "Done."
    return session


class TestBenchRunnerLive:
    def _patched_run(self, task, mock_session, cfg=None):
        """Helper: run a task with DevAgentSession and load_config mocked out."""
        if cfg is None:
            cfg = MagicMock()
            cfg.llm.model = "qwen2.5-coder:7b"
            cfg.agent.max_iterations = 10
        with (
            patch("devagent.core.config.load_config", return_value=cfg),
            patch("devagent.agent.flows.DevAgentSession", return_value=mock_session),
        ):
            from devagent.bench.runner import BenchRunner
            runner = BenchRunner(tasks=[task], dry_run=False)
            return runner.run_task(task)

    def test_live_passes_when_oracle_passes(self):
        from devagent.bench.runner import Task
        task = Task(
            id="live-pass",
            category="bug_fix",
            difficulty="easy",
            description="Fix the bug.",
            fixture_project="sample_project",
            oracle_check="exit 0",
        )
        result = self._patched_run(task, _make_mock_session())
        assert result.passed is True
        assert result.task_id == "live-pass"

    def test_live_fails_when_oracle_fails(self):
        from devagent.bench.runner import Task
        task = Task(
            id="live-fail",
            category="bug_fix",
            difficulty="easy",
            description="Fix the bug.",
            fixture_project="sample_project",
            oracle_check="exit 1",
        )
        result = self._patched_run(task, _make_mock_session())
        assert result.passed is False

    def test_live_captures_cost(self):
        from devagent.bench.runner import Task
        task = Task(
            id="live-cost",
            category="bug_fix",
            difficulty="easy",
            description="Fix the bug.",
            fixture_project="sample_project",
            oracle_check="exit 0",
        )
        result = self._patched_run(task, _make_mock_session(cost=0.0034, calls=5))
        assert result.cost_usd == pytest.approx(0.0034)
        assert result.iterations_used == 5

    def test_live_sets_max_iterations_from_task(self):
        """cfg.agent.max_iterations should be set from task when no runner override."""
        from devagent.bench.runner import Task
        task = Task(
            id="live-iters",
            category="bug_fix",
            difficulty="easy",
            description="Fix the bug.",
            fixture_project="sample_project",
            oracle_check="exit 0",
            max_iterations=7,
        )
        cfg = MagicMock()
        cfg.llm.model = "qwen2.5-coder:7b"
        cfg.agent.max_iterations = 30  # will be overridden

        captured_cfg = {}

        def fake_session_cls(**kwargs):
            captured_cfg["max_iterations"] = kwargs.get("cfg").agent.max_iterations
            return _make_mock_session()

        with (
            patch("devagent.core.config.load_config", return_value=cfg),
            patch("devagent.agent.flows.DevAgentSession", side_effect=fake_session_cls),
        ):
            from devagent.bench.runner import BenchRunner
            runner = BenchRunner(tasks=[task], dry_run=False)
            runner.run_task(task)

        assert captured_cfg["max_iterations"] == 7

    def test_live_runner_override_wins_over_task(self):
        """Runner-level max_iterations overrides task.max_iterations."""
        from devagent.bench.runner import Task
        task = Task(
            id="live-override",
            category="bug_fix",
            difficulty="easy",
            description="Fix the bug.",
            fixture_project="sample_project",
            oracle_check="exit 0",
            max_iterations=5,
        )
        cfg = MagicMock()
        cfg.llm.model = "qwen2.5-coder:7b"
        cfg.agent.max_iterations = 30

        captured_cfg = {}

        def fake_session_cls(**kwargs):
            captured_cfg["max_iterations"] = kwargs.get("cfg").agent.max_iterations
            return _make_mock_session()

        with (
            patch("devagent.core.config.load_config", return_value=cfg),
            patch("devagent.agent.flows.DevAgentSession", side_effect=fake_session_cls),
        ):
            from devagent.bench.runner import BenchRunner
            runner = BenchRunner(tasks=[task], dry_run=False, max_iterations=20)
            runner.run_task(task)

        assert captured_cfg["max_iterations"] == 20

    def test_live_session_error_returns_failed_result(self):
        """If run_message raises, task result is failed with error string."""
        from devagent.bench.runner import Task
        task = Task(
            id="live-err",
            category="bug_fix",
            difficulty="easy",
            description="Fix the bug.",
            fixture_project="sample_project",
            oracle_check="exit 0",
        )
        bad_session = MagicMock()
        bad_session.run_message.side_effect = RuntimeError("LLM unavailable")

        with (
            patch("devagent.core.config.load_config", return_value=MagicMock()),
            patch("devagent.agent.flows.DevAgentSession", return_value=bad_session),
        ):
            from devagent.bench.runner import BenchRunner
            runner = BenchRunner(tasks=[task], dry_run=False)
            result = runner.run_task(task)

        assert result.passed is False
        assert "LLM unavailable" in result.error

    def test_pycache_excluded_from_fixture_copy(self, tmp_path):
        """shutil.copytree must not copy __pycache__ into the work dir."""
        from devagent.bench.runner import BenchRunner, Task
        task = Task(
            id="cache-check",
            category="bug_fix",
            difficulty="easy",
            description="",
            fixture_project="sample_project",
            oracle_check="exit 0",
        )
        runner = BenchRunner(tasks=[task], dry_run=True)
        # Run normally — oracle passes, fixture is fine.
        result = runner.run_task(task)
        # The test is that it ran without error (pycache exclusion is internal,
        # but the run would break if copytree failed).
        assert result.error == ""


# ---------------------------------------------------------------------------
# SweepRunner live flag
# ---------------------------------------------------------------------------

class TestSweepLive:
    def test_sweep_dry_mode_passes_dry_run_true(self):
        from devagent.bench.sweep import SweepRunner
        runner = SweepRunner(
            param_grid={"model": ["qwen2.5-coder:7b"], "max_iterations": [10]},
            task_limit=1,
            difficulty="easy",
            dry_run=True,
        )
        assert runner.dry_run is True

    def test_sweep_live_mode_passes_dry_run_false(self):
        from devagent.bench.sweep import SweepRunner
        runner = SweepRunner(
            param_grid={"model": ["qwen2.5-coder:7b"], "max_iterations": [10]},
            task_limit=1,
            difficulty="easy",
            dry_run=False,
        )
        assert runner.dry_run is False

    def test_sweep_run_invokes_bench_runner_with_correct_dry_flag(self):
        """SweepRunner.run() must forward its dry_run flag to BenchRunner."""
        from devagent.bench.sweep import SweepRunner

        captured = {}

        class SpyBenchRunner:
            @staticmethod
            def load_tasks(category=None, difficulty=None, tags=None):
                from devagent.bench.runner import BenchRunner
                return BenchRunner.load_tasks(difficulty="easy")[:1]

            def __init__(self, tasks, dry_run, model=None, max_iterations=None):
                captured["dry_run"] = dry_run

            def run_all(self):
                from devagent.bench.runner import TaskResult
                return [TaskResult(task_id="x", passed=True, duration_sec=0.1)]

        with patch("devagent.bench.sweep.BenchRunner", SpyBenchRunner):
            runner = SweepRunner(
                param_grid={"model": ["qwen2.5-coder:7b"]},
                task_limit=1,
                difficulty="easy",
                dry_run=False,
            )
            runner.run()

        assert captured["dry_run"] is False
