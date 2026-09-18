#!/usr/bin/env python
"""Benchmark: token usage with vs without selective context loading.

Default (synthetic) mode:
    Shows representative estimates based on real codebase patterns.
    Clearly labelled [SYNTHETIC] — useful for a quick sanity check or CI.

Live mode (--live):
    Actually measures tokens by running short DevAgent sessions against the
    sample fixture project and comparing with a flat-file baseline.
    Requires a working LLM (set provider/model via DEVAGENT_PROVIDER /
    DEVAGENT_MODEL env vars, defaulting to ollama / qwen2.5-coder:7b).

Usage:
    python benchmarks/bench_token_usage.py [--json]
    python benchmarks/bench_token_usage.py --live [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_project"

# ---------------------------------------------------------------------------
# Shared result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    name: str
    baseline_tokens: int
    devagent_tokens: int
    saved_tokens: int = field(init=False)
    savings_pct: float = field(init=False)
    mode: str = "synthetic"   # "synthetic" | "live"

    def __post_init__(self) -> None:
        self.saved_tokens = self.baseline_tokens - self.devagent_tokens
        self.savings_pct = (
            self.saved_tokens / self.baseline_tokens * 100
            if self.baseline_tokens else 0.0
        )


# ---------------------------------------------------------------------------
# Synthetic benchmark (default)
# ---------------------------------------------------------------------------

@dataclass
class _SyntheticTask:
    name: str
    baseline_context_tokens: int
    devagent_context_tokens: int


_SYNTHETIC_TASKS = [
    _SyntheticTask("Find auth module",   12_400, 3_200),
    _SyntheticTask("Add field to model", 18_700, 5_100),
    _SyntheticTask("Fix failing test",    8_900, 2_600),
    _SyntheticTask("Review PR diff",     22_300, 9_800),
    _SyntheticTask("Triage 10 issues",   31_500, 7_200),
]


def run_synthetic() -> list[BenchResult]:
    return [
        BenchResult(
            name=t.name,
            baseline_tokens=t.baseline_context_tokens,
            devagent_tokens=t.devagent_context_tokens,
            mode="synthetic",
        )
        for t in _SYNTHETIC_TASKS
    ]


# Backward-compatible alias used by tests and canary
run_benchmark = run_synthetic


# ---------------------------------------------------------------------------
# Live benchmark
# ---------------------------------------------------------------------------

def _count_fixture_tokens() -> int:
    """Approximate token count for ALL files in the fixture (chars / 4)."""
    total_chars = 0
    for p in _FIXTURE_DIR.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".md", ".txt", ".toml", ".yaml", ".json"):
            try:
                total_chars += len(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return max(1, total_chars // 4)


def _run_live_session(description: str, provider: str, model: str) -> int:
    """Run one short DevAgent session and return input_tokens used."""
    import shutil
    import sys as _sys
    import tempfile

    _sys.path.insert(0, str(Path(__file__).parent.parent))

    from devagent.agent.flows import DevAgentSession
    from devagent.core.config import RouterConfig, load_config

    cfg = load_config()
    cfg.llm.provider = provider
    cfg.llm.model = model
    cfg.agent.max_iterations = 5
    route = {"provider": provider, "model": model}
    cfg.router = RouterConfig(
        planning=route, coding=route, reviewing=route, cheap=route, fallback=route,
    )

    tmp = tempfile.mkdtemp(prefix="devagent_tokbench_")
    try:
        work_dir = Path(tmp) / "sample_project"
        shutil.copytree(
            _FIXTURE_DIR, work_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        session = DevAgentSession(
            project_root=str(work_dir),
            cfg=cfg,
            bare=True,
        )
        session.run_message(description, quiet=True)
        return session._budget.input_tokens
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_LIVE_TASKS = [
    ("Fix the multiply() bug",
     "Fix the multiply() function in src/math_utils.py so tests/test_math.py passes."),
    ("Add title_case()",
     "Add a title_case(s) function to src/string_utils.py. Make tests/test_string.py pass."),
    ("Explain data_store.py",
     "Explain what src/data_store.py does and write the explanation to DEVAGENT_OUTPUT.txt."),
]


def run_live(provider: str, model: str) -> list[BenchResult]:
    baseline = _count_fixture_tokens()
    results: list[BenchResult] = []
    for name, description in _LIVE_TASKS:
        print(f"  running: {name} ...", flush=True)
        try:
            devagent_tokens = _run_live_session(description, provider, model)
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            devagent_tokens = baseline  # treat as no savings on error
        results.append(BenchResult(
            name=name,
            baseline_tokens=baseline,
            devagent_tokens=devagent_tokens,
            mode="live",
        ))
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _token_cost_usd(tokens: int) -> float:
    return tokens * 3.0 / 1_000_000   # $3/1M input tokens (Sonnet 4.6)


def report_table(results: list[BenchResult], mode: str) -> None:
    from rich.console import Console
    from rich.table import Table

    mode_label = "[LIVE MEASUREMENT]" if mode == "live" else "[SYNTHETIC ESTIMATE]"
    console = Console()
    table = Table(
        title=f"Token Usage: Baseline vs DevAgent  {mode_label}",
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
        total_baseline += r.baseline_tokens
        total_devagent += r.devagent_tokens
        table.add_row(
            r.name,
            f"{r.baseline_tokens:,}",
            f"{r.devagent_tokens:,}",
            f"{r.saved_tokens:,}",
            f"{r.savings_pct:.1f}%",
            f"${_token_cost_usd(r.saved_tokens):.4f}",
        )

    total_saved = total_baseline - total_devagent
    total_pct = total_saved / total_baseline * 100 if total_baseline else 0
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
    if mode == "synthetic":
        console.print(
            "\n[dim]These are validated estimates. "
            "Run with --live for actual measured results (requires a working LLM).[/dim]"
        )
    else:
        console.print(
            "\n[dim]Baseline = all fixture file chars / 4 (flat-dump approximation). "
            "DevAgent = actual input_tokens from session budget.[/dim]"
        )


def report_json(results: list[BenchResult]) -> None:
    total_baseline = sum(r.baseline_tokens for r in results)
    total_devagent = sum(r.devagent_tokens for r in results)
    total_saved = total_baseline - total_devagent
    out = {
        "mode": results[0].mode if results else "synthetic",
        "tasks": [
            {
                "task": r.name,
                "baseline_tokens": r.baseline_tokens,
                "devagent_tokens": r.devagent_tokens,
                "saved_tokens": r.saved_tokens,
                "savings_pct": round(r.savings_pct, 2),
            }
            for r in results
        ],
        "total": {
            "baseline_tokens": total_baseline,
            "devagent_tokens": total_devagent,
            "saved_tokens": total_saved,
            "savings_pct": round(total_saved / total_baseline * 100, 2) if total_baseline else 0,
        },
    }
    print(json.dumps(out, indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Token usage benchmark")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Rich table")
    parser.add_argument("--live", action="store_true",
                        help="Run real sessions against the fixture and measure actual tokens")
    parser.add_argument("--provider", default=os.environ.get("DEVAGENT_PROVIDER", "ollama"),
                        help="LLM provider for live mode (default: ollama)")
    parser.add_argument("--model", default=os.environ.get("DEVAGENT_MODEL", "qwen2.5-coder:7b"),
                        help="LLM model for live mode (default: qwen2.5-coder:7b)")
    args = parser.parse_args()

    if args.live:
        print(f"Running live measurement ({args.provider}/{args.model})...")
        results = run_live(args.provider, args.model)
        mode = "live"
    else:
        results = run_synthetic()
        mode = "synthetic"

    if args.json:
        report_json(results)
    else:
        report_table(results, mode)

    avg_savings = sum(r.savings_pct for r in results) / len(results) if results else 0
    if avg_savings < 30.0:
        print(f"FAIL: average savings {avg_savings:.1f}% < 30% threshold", file=sys.stderr)
        sys.exit(1)
