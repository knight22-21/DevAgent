# DevAgent Leaderboard

_Last updated: 2026-09-24_

Scores are from `devagent bench native --live` runs against the full task set.
Pass = oracle exits 0 after the agent loop. Higher is better.

| Rank | Model | Provider | Best Score | Latest Score | Latest Run | Runs | Avg Time |
|------|-------|----------|------------|--------------|------------|------|----------|
| 1 | `gpt-oss:20b` | Ollama Cloud | **21/24 (87%)** | 21/24 (87%) | 2026-09-18 | 2 | 43.9s |
| 2 | `llama3.2:3b` | Ollama local | **9/20 (45%)** | 9/20 (45%) | 2026-09-07 | 1 | 45.0s |

> This table is auto-updated by CI after every push to main. Pre-existing runs are seeded
> from documented results in BENCHMARKS.md. New runs using `--model` and `--provider`
> flags populate the leaderboard automatically.

---

To add your model to this leaderboard:

```bash
devagent bench native --live --model <your-model> --provider <ollama|anthropic|openai>
```

Results are saved automatically to `benchmarks/results/` and picked up next time
`devagent bench leaderboard` runs.
