# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
