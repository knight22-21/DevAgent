# DevAgent Benchmarks

DevAgent ships with a built-in task benchmark that measures agent performance on 20 real coding tasks. Each task runs the full agent loop against a fixture Python project and passes only if the oracle (a `pytest` run or a `python -c` assertion) exits 0.

---

## Task set

20 tasks across 6 categories, covering what a real agent session looks like day-to-day:

| Category | Tasks | What it tests |
|---|---|---|
| `bug_fix` | 4 | Identify and fix a broken function; all existing tests must still pass |
| `feature_add` | 3 | Add a new function or class with tests that pass |
| `refactor` | 3 | Restructure code without changing observable behaviour |
| `test_write` | 2 | Write a comprehensive test file from scratch |
| `security` | 3 | Remove `eval()` vulnerabilities, audit for security issues |
| `explain` | 2 | Read code, write a structured explanation to `DEVAGENT_OUTPUT.txt` |
| `onboarding` | 1 | Explore an unfamiliar codebase and write a developer guide |
| `multi_file` | 2 | Fix or add features across multiple files in one pass |

Difficulty distribution: 7 easy, 8 medium, 5 hard.

---

## Results

### gpt-oss:20b — Ollama Cloud — September 2026

**20/20 (100%)**

| Task | Category | Difficulty | Result | Time (s) | Iterations |
|---|---|---|---|---|---|
| bug-fix-001 | bug_fix | easy | PASS | 26.8 | 8 |
| feature-add-001 | feature_add | easy | PASS | 29.7 | 10 |
| security-fix-001 | security | medium | PASS | 33.2 | 11 |
| bug-fix-002 | bug_fix | easy | PASS | 37.5 | 11 |
| refactor-001 | refactor | medium | PASS | 30.8 | 10 |
| explain-001 | explain | easy | PASS | 12.7 | 3 |
| test-write-001 | test_write | medium | PASS | 32.5 | 10 |
| code-review-001 | security | medium | PASS | 51.3 | 4 |
| feature-add-002 | feature_add | medium | PASS | 31.3 | 10 |
| bug-fix-003 | bug_fix | easy | PASS | 42.0 | 11 |
| multi-file-001 | multi_file | hard | PASS | 46.8 | 14 |
| security-audit-001 | security | hard | PASS | 24.5 | 9 |
| refactor-002 | refactor | medium | PASS | 36.9 | 15 |
| feature-add-003 | feature_add | hard | PASS | 53.8 | 15 |
| explain-002 | explain | easy | PASS | 12.6 | 7 |
| bug-fix-004 | bug_fix | medium | PASS | 30.8 | 11 |
| test-write-002 | test_write | medium | PASS | 81.1 | 14 |
| refactor-003 | refactor | hard | PASS | 87.2 | 11 |
| multi-file-002 | multi_file | hard | PASS | 34.0 | 11 |
| onboarding-001 | onboarding | easy | PASS | 16.9 | 9 |

Average time per task: **36.9s** — Average iterations: **9.7**

---

### llama3.2:3b — Ollama (local) — September 2026

**9/20 (45%)**

| Task | Category | Difficulty | Result | Notes |
|---|---|---|---|---|
| bug-fix-001 | bug_fix | easy | PASS | |
| feature-add-001 | feature_add | easy | PASS | |
| security-fix-001 | security | medium | FAIL | Timeout — model hung on first Ollama call |
| bug-fix-002 | bug_fix | easy | FAIL | Timeout |
| refactor-001 | refactor | medium | PASS | |
| explain-001 | explain | easy | PASS | Auto-captured from final text reply |
| test-write-001 | test_write | medium | PASS | |
| code-review-001 | security | medium | FAIL | Output lacked required keywords |
| feature-add-002 | feature_add | medium | PASS | |
| bug-fix-003 | bug_fix | easy | FAIL | Timeout |
| multi-file-001 | multi_file | hard | FAIL | Timeout (120s) |
| security-audit-001 | security | hard | FAIL | Timeout (120s) |
| refactor-002 | refactor | medium | FAIL | ImportError — model broke imports rewriting file |
| feature-add-003 | feature_add | hard | FAIL | Test names didn't match oracle `-k update` |
| explain-002 | explain | easy | PASS | |
| bug-fix-004 | bug_fix | medium | FAIL | Oracle SyntaxError (apostrophe in shell command) |
| test-write-002 | test_write | medium | FAIL | Timeout (90s) |
| refactor-003 | refactor | hard | PASS | |
| multi-file-002 | multi_file | hard | FAIL | Test deselected — wrong test name |
| onboarding-001 | onboarding | easy | PASS | Needed 15 iterations |

Primary failure modes: **5 timeouts** (model hung waiting for Ollama on complex tasks), **3 import errors** (model rewrote `.py` files breaking imports), **2 test-name mismatches** (model didn't follow the oracle's `-k` filter pattern).

---

## Summary comparison

| Model | Provider | Pass Rate | Avg time/task | Notes |
|---|---|---|---|---|
| llama3.2:3b | Ollama local | 9/20 (45%) | ~45s | Frequent timeouts on medium/hard tasks |
| **gpt-oss:20b** | **Ollama Cloud** | **20/20 (100%)** | **36.9s** | No timeouts; solid tool-call compliance |

---

## B4 — Cost-to-correctness sweep

Answers: *"Which model gives the best value for real coding tasks?"*

Run on 5 tasks from the native set (bug_fix, feature_add, security, refactor categories), both models on Ollama Cloud — September 2026.

```bash
devagent bench sweep --live --params model --tasks 5 --provider ollama
```

| Model | Pass Rate | Avg time/task | Notes |
|---|---|---|---|
| **gpt-oss:20b** | **5/5 (100%)** | **38.6s** | Solid tool-call compliance; reads files, writes code, verifies with tests |
| glm-5.3-flash | 2/5 (40%) | 3.0s | Responds fast but skips the tool-call loop; fails oracle checks |

**Takeaway:** glm-5.3-flash's 3s average reflects that it completes turns without doing the work — it answers immediately rather than reading files, writing code, and running tests. gpt-oss:20b takes longer because it actually executes each step. For agent tasks, time-per-task is not a measure of efficiency; pass rate is.

---

## Running the benchmark

**Dry run (oracle only, no LLM):**

```bash
devagent bench native
```

Verifies the oracle/fixture infrastructure without invoking the agent. Used by CI.

**Live run against a model:**

```bash
# Local Ollama
devagent bench native --live --model qwen2.5-coder:7b --provider ollama

# Ollama Cloud (requires OLLAMA_HOST and OLLAMA_API_KEY in .env)
devagent bench native --live --model gpt-oss:20b --provider ollama

# Anthropic
devagent bench native --live --model claude-sonnet-4-6 --provider anthropic
```

**Filter by category or difficulty:**

```bash
devagent bench native --live --category bug_fix
devagent bench native --live --difficulty easy
devagent bench native --live -t feature-add-003   # single task by ID
```

Results are always saved to `benchmarks/results/<timestamp>.json`. A rolling `native_partial.json` is written after each task so a crash mid-run doesn't lose completed results.

---

## Stored results

| File | Model | Pass rate | Date |
|---|---|---|---|
| `benchmarks/results/llama32_3b_baseline.json` | llama3.2:3b (local) | 9/20 (45%) | Sep 2026 |
| `benchmarks/results/native_20260907_074033.json` | gpt-oss:20b (cloud) | 20/20 (100%) | Sep 2026 |
| `benchmarks/results/sweep_20260907_171806.json` | B4 sweep: gpt-oss:20b vs glm-5.3-flash | 5/5 vs 2/5 | Sep 2026 |
