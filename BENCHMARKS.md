# DevAgent Benchmarks

DevAgent ships with a built-in task benchmark that measures agent performance on 24 real coding tasks across Python, JavaScript, and Go. Each task runs the full agent loop against a fixture project and passes only if the oracle (a test runner or assertion command) exits 0.

---

## Task set

24 tasks across 8 categories and 3 languages:

### Python (20 tasks) — fixture: `sample_project`

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

### JavaScript (2 tasks) — fixture: `js_project`, oracle: `node --test`

| Task | What it tests |
|---|---|
| `js-bug-fix-001` | Fix deliberate bug in `divide()` (`a + b` instead of `a / b`) |
| `js-feature-001` | Implement missing `camelCase()` function in strings.js |

### Go (2 tasks) — fixture: `go_project`, oracle: `go test`

| Task | What it tests |
|---|---|
| `go-bug-fix-001` | Fix deliberate bug in `Multiply()` (`a + b` instead of `a * b`) |
| `go-feature-001` | Implement missing `TitleCase()` function in strings.go |

Difficulty distribution (Python): 7 easy, 8 medium, 5 hard.

---

## Results

### gpt-oss:20b — Ollama Cloud — September 2026 (24-task run, JS + Go added)

**21/24 (87.5%)**

| Task | Language | Category | Result | Time (s) | Iterations | Notes |
|---|---|---|---|---|---|---|
| bug-fix-001 | Python | bug_fix | PASS | 39.3 | 9 | |
| feature-add-001 | Python | feature_add | PASS | 47.7 | 10 | |
| security-fix-001 | Python | security | PASS | 43.6 | 11 | |
| bug-fix-002 | Python | bug_fix | PASS | 50.0 | 11 | |
| refactor-001 | Python | refactor | PASS | 51.2 | 11 | |
| explain-001 | Python | explain | PASS | 18.9 | 4 | |
| test-write-001 | Python | test_write | PASS | 44.8 | 10 | |
| code-review-001 | Python | security | FAIL | 60.0 | 0 | Timeout — model hung on first call |
| feature-add-002 | Python | feature_add | PASS | 74.2 | 11 | |
| bug-fix-003 | Python | bug_fix | PASS | 47.1 | 10 | |
| multi-file-001 | Python | multi_file | PASS | 35.3 | 12 | |
| security-audit-001 | Python | security | PASS | 36.6 | 15 | |
| refactor-002 | Python | refactor | FAIL | 48.9 | 15 | Added type hints but broke `multiply()` |
| feature-add-003 | Python | feature_add | PASS | 81.2 | 12 | |
| explain-002 | Python | explain | PASS | 15.5 | 7 | |
| bug-fix-004 | Python | bug_fix | PASS | 39.3 | 11 | |
| test-write-002 | Python | test_write | FAIL | 72.6 | 11 | Called `truncate("")` missing required arg |
| refactor-003 | Python | refactor | PASS | 53.9 | 11 | |
| multi-file-002 | Python | multi_file | PASS | 47.8 | 10 | |
| onboarding-001 | Python | onboarding | PASS | 22.0 | 10 | |
| js-bug-fix-001 | JavaScript | bug_fix | PASS | 13.2 | 6 | |
| js-feature-001 | JavaScript | feature_add | PASS | 12.3 | 6 | |
| go-bug-fix-001 | Go | bug_fix | PASS | 16.0 | 5 | |
| go-feature-001 | Go | feature_add | PASS | 21.7 | 7 | |

**By language:** Python 17/20 (85%) · JavaScript 2/2 (100%) · Go 2/2 (100%)

Average time per task: **43.9s** — Average iterations: **9.5**

---

### gpt-oss:20b — Ollama Cloud — September 2026 (original 20-task Python-only run)

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

### gpt-oss:120b — Ollama Cloud — November 2026

**2/24 (8%)** under the corrected benchmark rules. Average: **5.2 LLM calls**, **4.1 tool calls**, and **13.3s/task**.
Artifact: `benchmarks/results/native_20261106_182542.json`.

The earlier 6/24 (25%) result used a runner fallback that could convert a final chat response into an output file and weaker text oracles. The corrected run requires explicit artifacts and semantic content, so 2/24 is the authoritative score.

### nemotron-3-ultra — Ollama Cloud — November 2026

**15/24 (62%)** under the same corrected rules. Average: **7.3 LLM calls**, **7.1 tool calls**, and **54.9s/task**.
Artifact: `benchmarks/results/native_20261106_184818.json`.

Nemotron passed the core Python feature, bug-fix, explanation, onboarding, and JavaScript tasks more often than gpt-oss:120b. Remaining failures were concentrated in multi-file Python work, one output review task, test generation, Go tasks, and timeouts.

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

| Model | Provider | Tasks | Pass Rate | Avg time/task | Notes |
|---|---|---|---|---|---|
| llama3.2:3b | Ollama local | 20 | 9/20 (45%) | ~45s | Frequent timeouts on medium/hard tasks |
| **gpt-oss:20b** | **Ollama Cloud** | **20** | **20/20 (100%)** | **36.9s** | Python-only baseline |
| **gpt-oss:20b** | **Ollama Cloud** | **24** | **21/24 (87.5%)** | **43.9s** | Full suite incl. JS + Go |

JS and Go tasks completed faster (avg 16s) and more efficiently (avg 6 iterations) than Python tasks — the agent needs fewer iterations on simpler single-file fixes in those languages.

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

**Latest gpt-oss:120b matrix (45 evaluations):** all combinations used the same five tasks (`bug-fix-001`, `feature-add-001`, `security-fix-001`, `bug-fix-002`, `refactor-001`).

| Max iterations | Effort | Pass rate |
|---:|---|---:|
| 10 | low | 40% |
| 10 | high | 60% |
| 10 | max | 60% |
| 30 | low | 60% |
| 30 | high | 40% |
| 30 | max | 60% |
| 50 | low | 40% |
| 50 | high | 60% |
| 50 | max | 60% |

**Cost note:** Ollama is currently treated as zero-cost by the budget layer, so these stored cost values are not Ollama Cloud billing estimates. Add model pricing metadata before using B4 for spend decisions.

**Finding:** increasing iteration budget did not improve correctness on this sample. The best observed result was 60%, achieved by several settings; `50/max` was not better than `10/max`. `security-fix-001` passed in 9/9 runs, `refactor-001` in 8/9, `bug-fix-002` in 0/9, and `feature-add-001` in 0/9. This indicates prompt/task execution failures, not a simple budget shortage.

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

**Filter by category, difficulty, or language:**

```bash
devagent bench native --live --category bug_fix
devagent bench native --live --difficulty easy
devagent bench native --live -t js-bug-fix-001   # single task by ID
devagent bench native --live -t go-feature-001
```

Results are always saved to `benchmarks/results/<timestamp>.json` with the run objective,
configuration, task count, and per-task details. A rolling `native_partial.json` is written
after each task so a crash mid-run doesn't lose completed results.

---

## Stored results

| File | Model | Tasks | Pass rate | Date |
|---|---|---|---|---|
| `benchmarks/results/llama32_3b_baseline.json` | llama3.2:3b (local) | 20 | 9/20 (45%) | Sep 2026 |
| `benchmarks/results/native_20260907_074033.json` | gpt-oss:20b (cloud) | 20 | 20/20 (100%) | Sep 2026 |
| `benchmarks/results/native_20260918_123726.json` | gpt-oss:20b (cloud) | 24 | 21/24 (87.5%) | Sep 2026 |
| `benchmarks/results/native_20261106_151314.json` | gpt-oss:120b (cloud) | 24 | 6/24 (25%) | Nov 2026 |
| `benchmarks/results/native_20261106_182542.json` | gpt-oss:120b corrected | 24 | 2/24 (8%) | Nov 2026 |
| `benchmarks/results/native_20261106_184818.json` | nemotron-3-ultra corrected | 24 | 15/24 (62%) | Nov 2026 |
| `benchmarks/results/sweep_20261106_152813.json` | gpt-oss:120b B4 matrix | 45 evaluations | 40–60%/configuration | Nov 2026 |
| `benchmarks/results/sweep_20260907_171806.json` | B4 sweep: gpt-oss:20b vs glm-5.3-flash | 5 | 5/5 vs 2/5 | Sep 2026 |
