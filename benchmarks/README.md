# DevAgent Benchmark Suite

The benchmark suite (`devagent/bench/`) measures DevAgent's ability to complete
real coding tasks end-to-end. Every task runs the full agent loop against an
isolated fixture project and passes only when a `pytest` or shell oracle exits 0.

---

## Quick start

```bash
# Dry-run: validate the oracle/fixture infrastructure (no LLM needed)
devagent bench native

# Live run against a model
devagent bench native --live --model gpt-oss:20b --provider ollama

# Run only specific tasks
devagent bench native --live -t bug-fix-001 -t refactor-002 --model gpt-oss:20b --provider ollama

# View the leaderboard
devagent bench leaderboard

# View cross-run history
devagent bench history
```

---

## Task set

`benchmarks/tasks/task_set.json` — 24 tasks across three fixture projects:

| Language | Tasks | Fixture project |
|---|---|---|
| Python | 20 | `benchmarks/fixtures/sample_project/` |
| JavaScript | 2 | `benchmarks/fixtures/js_project/` |
| Go | 2 | `benchmarks/fixtures/go_project/` |

### Task categories

| Category | Description | Count |
|---|---|---|
| `bug_fix` | Fix an intentional bug so tests pass | 5 |
| `feature_add` | Implement a new function or module | 5 |
| `refactor` | Restructure code without changing behaviour | 3 |
| `test_write` | Write a test suite for existing code | 4 |
| `security_audit` | Find and document security issues | 2 |
| `onboarding` | Explain what a module does | 2 |
| `code_review` | Review a PR diff for bugs | 1 |
| `feature_add` (JS/Go) | Add a feature in non-Python language | 2 |

### Task schema

```json
{
  "id": "bug-fix-001",
  "category": "bug_fix",
  "difficulty": "easy",
  "description": "What the user types to the agent",
  "fixture_project": "sample_project",
  "oracle_check": "python -m pytest tests/test_math.py -q",
  "oracle_pass_exit_code": 0,
  "expected_files_touched": ["src/math_utils.py"],
  "max_iterations": 30,
  "timeout_sec": 120,
  "tags": ["python", "pytest"]
}
```

---

## Benchmark scores

Results from live runs with `devagent bench native --live`:

| Model | Provider | Score | Run date |
|---|---|---|---|
| **gpt-oss:20b** | Ollama Cloud | **21/24 (87.5%)** | 2026-09-18 |
| llama3.2:3b | Ollama (local) | 9/20 (45%) | 2026-09-07 |

The leaderboard is auto-updated after every push to main. See
[LEADERBOARD.md](../LEADERBOARD.md) for the latest rankings.

---

## Running benchmarks

### Dry-run (CI / no LLM)

The dry-run copies each fixture to a temp dir and runs the oracle on the
**unmodified** fixture. Oracles that require agent changes will fail — this is
expected and intentional. The dry-run validates the framework (task loading,
fixture copying, oracle execution) without calling any LLM.

```bash
devagent bench native          # all 24 tasks
devagent bench canary          # 5 canary tasks + framework checks (used in CI)
```

### Live run (requires a running LLM)

```bash
# Full run
devagent bench native --live --model gpt-oss:20b --provider ollama

# Filter by category or difficulty
devagent bench native --live --category bug_fix --model gpt-oss:20b --provider ollama
devagent bench native --live --difficulty easy   --model gpt-oss:20b --provider ollama

# Run specific tasks (repeatable -t flag)
devagent bench native --live -t bug-fix-001 -t test-write-001 --model gpt-oss:20b --provider ollama
```

Results are saved to `benchmarks/results/native_YYYYMMDD_HHMMSS.json` automatically.

### Leaderboard

```bash
# From local results
devagent bench leaderboard

# Fetch results committed to the bench-results branch
devagent bench leaderboard --remote

# Write to LEADERBOARD.md
devagent bench leaderboard --remote --output LEADERBOARD.md
```

### Cross-run history

```bash
# Show pass/fail trend from local result files
devagent bench history

# Include results from the bench-results branch
devagent bench history --remote
```

---

## CI integration

`.github/workflows/canary.yml` runs `devagent bench canary` on every PR.
The canary does not require a real LLM — it runs framework checks and dry-run
oracle validation. CI fails if the canary pass rate drops below 80%.

`.github/workflows/bench-persist.yml` runs on every push to main:
1. Runs `devagent bench canary --save-json` and `devagent bench native --dry`
2. Commits JSON result files to the `bench-results` orphan branch
3. Regenerates `LEADERBOARD.md` on main via `devagent bench leaderboard --remote`

---

## Result file format

Saved result files use a `{"meta": {...}, "results": [...]}` envelope:

```json
{
  "meta": {
    "model": "gpt-oss:20b",
    "provider": "ollama",
    "timestamp": "2026-09-18T12:37:26"
  },
  "results": [
    {
      "task_id": "bug-fix-001",
      "passed": true,
      "duration_sec": 28.4,
      "iterations_used": 5,
      "cost_usd": 0.0,
      "oracle_output": "1 passed in 0.12s",
      "files_touched": ["src/math_utils.py"],
      "files_missed": []
    }
  ]
}
```

Old result files (plain list format) are also supported for backward compatibility.

---

## Adding new tasks

1. Add a fixture project under `benchmarks/fixtures/<name>/` with a working test
   suite that can serve as the oracle.
2. Add the task definition to `benchmarks/tasks/task_set.json`.
3. Run `devagent bench native -t <your-new-task-id>` in dry-run mode — the oracle
   should fail (since the fixture is unmodified).
4. Run with `--live` to verify an agent can complete the task.
5. Add the task to `benchmarks/tasks/canary.json` if it is fast (< 30s dry-run).
