# DevAgent Leaderboard

_Last updated: 2026-11-07_

Scores are from `devagent bench native --live` runs against the full task set.
Pass = oracle exits 0 after the agent loop. Higher is better.

| Rank | Model | Provider | Best Score | Latest Score | Latest Run | Runs | Avg Time |
|------|-------|----------|------------|--------------|------------|------|----------|
| 1 | `gpt-oss:20b` | ollama | **21/24 (88%)** | 21/24 (88%) | 2026-09-18 | 2 | 43.9s |
| 2 | `nemotron-3-ultra` | ollama cloud | **15/24 (62%)** | 15/24 (62%) | 2026-11-07 | 1 | 54.9s |
| 3 | `llama3.2:3b` | ollama | **9/20 (45%)** | 9/20 (45%) | 2026-09-07 | 1 | ~45s |
| 4 | `gpt-oss:120b` | ollama cloud | **6/24 (25%)** | **2/24 (8%) corrected** | 2026-11-07 | 3 | 13.3s |

---

To add your model to this leaderboard:

```bash
devagent bench native --live --model <your-model> --provider <ollama|anthropic|openai>
```

Results are saved automatically to `benchmarks/results/` and picked up next time
`devagent bench leaderboard` runs.
