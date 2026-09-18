# Contributing to DevAgent

Thank you for your interest in contributing! DevAgent is open source under the MIT license.

## Quick start

```bash
git clone https://github.com/yourusername/DevAgent.git
cd DevAgent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest tests/          # all tests should pass
```

## Project layout

```
devagent/
  agent/          # AgentLoop, flows (implement, review, triage, fix-ci)
  core/           # Config, LLM client, router, models
  codeprism/      # CodePrism knowledge graph client + tools
  output/         # Rich terminal renderer
  server/         # REST server stub (devagent serve)
  session/        # SQLite-backed session store + memory
  tools/          # Tool registry + built-in tools (file, shell, git, GitHub, memory)
  watcher/        # Repo health monitor (async scheduler)
  cli.py          # Typer CLI — all commands live here
tests/            # pytest suite (no mocked DB, integration-friendly)
benchmarks/       # Token, security, and task-completion benchmarks
docs/             # Guides: plugin tools, REST API, architecture
```

## Making changes

1. **Branch** from `main`: `git checkout -b feat/my-feature`
2. **Write tests first** when adding features — run `pytest -x` to stay green
3. **Lint**: `ruff check devagent/ tests/` (zero warnings required for CI)
4. **No LangGraph / LangChain** — pure Python with official SDKs only
5. **No forced commits/pushes** — the agent respects that the user owns git operations

## Adding a plugin tool

Tools are just callables registered in the `ToolRegistry`. They do not need to live in `devagent/tools/` — any third-party package can register tools at runtime.

```python
from devagent.tools.registry import ToolRegistry

def my_tool(args: dict) -> str:
    """Return a string result. Never raise — return '[error] ...' instead."""
    query = args.get("query", "")
    return f"Result for: {query}"

def register(registry: ToolRegistry) -> None:
    registry.register(
        name="my_search",
        description=(
            "Search a custom knowledge base. "
            "Use this when the user asks about internal documentation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
        handler=my_tool,
    )
```

See `docs/plugin_tools.md` for the full guide.

## CI

GitHub Actions runs on every PR:
- **Lint** — `ruff check`
- **Test** — `pytest` on Python 3.12 and 3.13
- **Build** — `python -m build` (wheel + sdist)

PyPI publish triggers on a new GitHub Release (Trusted Publishing, no stored secrets).

## Commit style

```
feat: add remember_fact tool to session memory
fix: router now caches LLMClient instances per task type
docs: add plugin tool guide
test: phase 5 repair loop edge cases
```

Type prefixes: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

## Code style

- Python 3.12+, type annotations everywhere
- `ruff` for linting — line length 100, target py312
- No mocks for the session DB — tests use real SQLite in temp dirs
- Tool handlers: always return `str`, never raise
- No print statements — use `rich.console.Console` or yield `AgentEvent`

## Opening a PR

- Keep PRs focused — one feature or fix per PR
- Update `CHANGELOG.md` under `[Unreleased]`
- Add or update tests for your change
- For new tools, add them to `docs/plugin_tools.md`

## Community

- **Bugs**: [GitHub Issues](https://github.com/yourusername/DevAgent/issues) — use the bug report template
- **Feature ideas**: [GitHub Issues](https://github.com/yourusername/DevAgent/issues) — use the feature request template
- **Questions**: Open a Discussion on GitHub
