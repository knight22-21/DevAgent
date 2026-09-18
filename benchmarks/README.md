# DevAgent Benchmarks

Three benchmark scripts that measure the key v1.0 quality claims.

## Running benchmarks

```bash
# All benchmarks (takes 2-5 minutes with Ollama running)
python benchmarks/bench_token_usage.py
python benchmarks/bench_security.py
python benchmarks/bench_tasks.py
```

All benchmarks use synthetic workloads — no real GitHub API calls, no real file writes.
They do call the configured LLM via `LLMClient` when `DEVAGENT_BENCH_LIVE=1` is set;
otherwise they use saved fixture responses.

## Benchmark summaries

### `bench_token_usage.py` — Token efficiency

Compares token usage for 5 representative tasks:
- **Baseline**: raw codebase dump in context (no CodePrism)
- **DevAgent**: CodePrism-compressed graph context injected per turn

Expected improvement: 40-70% fewer tokens for large codebases (>10k lines).

### `bench_security.py` — Security detection rate

Runs 20 write operations through the security gate:
- 10 safe writes → expect 0 blocked
- 6 known-bad patterns (eval, shell injection, path traversal, etc.) → expect 6 blocked
- 4 WARN-level writes → expect 4 prompted

Target: 100% detection of known-bad patterns, 0% false positives on safe writes.

### `bench_tasks.py` — Task completion rate

Simulates 10 agent tasks end-to-end with a mock LLM:
- Edit a file + pass tests
- Create a new module
- Fix a CI failure (injected as tool result)
- Triage 5 issues (mock GitHub responses)

Target: 9/10 tasks complete within 10 iterations (1 allowed to hit MAX_ITERATIONS).
