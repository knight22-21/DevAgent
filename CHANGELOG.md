# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-09-25

### Added
- 24-task benchmark set covering Python (20), JavaScript (2), and Go (2) fixture projects
- JS fixture project (`js_project/`) with `add-feature-001` and `test-write-js-001` tasks
- Go fixture project (`go_project/`) with `add-feature-go-001` and `test-write-go-001` tasks
- `devagent bench leaderboard` command — groups results by (model, provider), shows best and latest score
- `devagent bench leaderboard --remote` — fetches results from `bench-results` git branch
- `devagent bench leaderboard --output <file>` — writes markdown leaderboard to a file
- `LEADERBOARD.md` seeded with live benchmark scores (gpt-oss:20b: 21/24, llama3.2:3b: 9/20)
- CI auto-update step in `bench-persist.yml`: regenerates `LEADERBOARD.md` on main after every push
- `devagent bench history --remote` flag for fetching result files from the `bench-results` branch
- Go binary validation in canary workflow (ensures Go fixtures compile before running)
- Native dry-run results persisted to `bench-results` branch alongside canary JSON
- Multi-task `-t` flag (repeatable): `devagent bench native -t bug-fix-001 -t refactor-002`
- Model/provider metadata embedded in saved benchmark JSON files for leaderboard tracking

### Fixed
- `code-review-001`: raised `timeout_sec` from 60 → 120 to prevent API call timeouts
- `refactor-002`: removed false task description premise ("multiply bug is already fixed"); agent now runs pytest first to discover and fix failures before adding type hints
- `test-write-002`: added explicit import pattern, "run each function via shell to verify expected values before writing assertions", and raised `timeout_sec` to 300
- Multi-task `-t` flag: switched from `str | None` to `list[str] | None` so multiple `-t` values accumulate correctly
- Unicode check marks in canary output replaced with ASCII for cross-platform terminal compatibility

### Changed
- Benchmark result JSON format extended: `{"meta": {...}, "results": [...]}` envelope (backward compatible with old plain-list format)
- `BenchReport.save_json` accepts optional `model` and `provider` parameters
- `BenchReport.render_leaderboard` and `generate_leaderboard_md` added to `report.py`

## [1.1.0] - 2026-08-28

### Added
- `INTEGRATIONS.md` — setup guides for Claude Code, ChatGPT, Antigravity, GitHub Copilot, Cursor, Windsurf, VS Code, JetBrains, Zed
- `BENCHMARKS.md` — full benchmark documentation with per-task results table
- Ollama Cloud provider support (`gpt-oss:20b`, `nemotron-3-nano:30b`, `gemma4:31b`, 15+ hosted models)
- First live 20-task benchmark run: gpt-oss:20b scored 20/20 (100%)
- B4 cost-to-correctness sweep infrastructure: `devagent bench sweep` with parameter grid
- `devagent bench history` command for cross-run trend comparison
- `expected_files_touched` enforcement in benchmark runner — reports files missed or extra
- Syntax checking for `.py` files written during benchmark runs (auto-surfaces errors to model)
- Token-savings measurement in `bench_token_usage.py` using real CodePrism graph queries
- Real `call_count` tracking for iteration counting in live benchmark runs
- Phases 10–14: hooks infrastructure, permission modes, REPL UX improvements, agent definition files

### Fixed
- Removed `--skip-legacy` from CI — all legacy benchmark scripts pass reliably
- Benchmark oracle fixes: `DEVAGENT_OUTPUT.txt` auto-write, syntax check, task-id filter

### Changed
- README overhauled to match the full current feature set (Phases 1–16 complete)

## [0.3.0] - 2026-08-13

### Added
- New `devagent watch` command to monitor a GitHub repository for newly opened issues
- Watcher storage, scheduler, and reporting flow for recurring repository health checks
- Cross-issue conflict detection to flag files touched by multiple open issues
- Watcher-specific terminal rendering for watched repos, health reports, and stored analyses

### Changed
- GitHub client now supports listing repository issues for watcher checks
- Configuration now includes watcher defaults such as interval, labels, and cross-conflict behavior
- Added `apscheduler` runtime support and enabled automatic asyncio handling for pytest

### Fixed
- Added watcher-focused tests covering conflict detection, analysis building, and watcher storage

## [0.2.0] - 2026-08-11

### Added
- Direct GitHub issue and pull request URL input for `devagent analyze` via `--url`
- Interactive terminal chat sessions for exploring a generated gap analysis
- Compact chat-focused report rendering and conversation history support
- Test coverage for GitHub URL parsing and chat prompt grounding

### Changed
- `devagent analyze` can now open a chat session immediately with `--chat`
- Pull request URLs are analyzed as specifications using PR title and description
- Spec analysis MCP server integration now uses `FastMCP`

### Fixed
- Configuration path resolution now supports the legacy `SPECSYNC_CONFIG_PATH` override
- Test imports and assertions were aligned with the `devagent` package naming

## [0.1.1] - 2026-08-10

### Fixed
- Initial bug fixes and stability improvements

## [0.1.0] - 2026-08-09

### Added
- Initial release of DevAgent
- Automated gap analysis between specifications and codebase
- Local LLM support via Ollama
- Model Context Protocol (MCP) integration
- Semantic search with ChromaDB
- Rich terminal UI and Markdown report generation
