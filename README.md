<div align="center">

# DevAgent

**An AI coding agent for your terminal. Offline-first, GitHub-native, benchmarked at 20/20 on real coding tasks.**

[![PyPI version](https://img.shields.io/pypi/v/devagent.svg)](https://pypi.org/project/devagent/)
[![Python Versions](https://img.shields.io/pypi/pyversions/devagent.svg)](https://pypi.org/project/devagent/)
[![License: MIT](https://img.shields.io/pypi/l/devagent.svg)](LICENSE)


</div>

---

DevAgent is a terminal-based AI coding agent that operates on your local codebase. You describe a task in plain language — implement this GitHub issue, review this pull request, fix the failing CI, refactor this module — and the agent reads your files, reasons about the code, makes changes, runs your tests, and reports what it did. It runs fully offline by default using Ollama and is built to complement whatever editor or AI tool you already use, not replace it.

---

## Table of contents

- [What problem it solves](#what-problem-it-solves)
- [How it works](#how-it-works)
- [Supported LLM providers](#supported-llm-providers)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Integrations](#integrations)
- [Benchmarks](#benchmarks)
- [Commands reference](#commands-reference)
- [GitHub workflows](#github-workflows)
- [Configuration](#configuration)
- [Session management](#session-management)
- [Security gate](#security-gate)
- [Background watcher](#background-watcher)
- [REST API](#rest-api)
- [Writing plugin tools](#writing-plugin-tools)
- [Contributing](#contributing)
- [License](#license)

---

## What problem it solves

Most AI coding tools fall into one of two categories: chat assistants that can reason about code but cannot actually run or edit it, and editor plugins that complete the next few lines but cannot handle multi-step tasks. Neither category handles the full loop of understanding a requirement, identifying which files need to change, making those changes, verifying them with tests, and committing a working result.

DevAgent is built to close that gap. It handles the execution layer — actually reading files, writing code, running commands, querying your version control history — while you stay in control of reviewing and accepting changes.

Three specific problems it addresses:

**Token cost and context quality.** When you paste a 2,000-line file into a chat window, most of that content is irrelevant to your question. DevAgent integrates with [CodePrism](https://pypi.org/project/codeprism-ai/), a persistent code knowledge graph built from your codebase's AST and import graph. The agent queries the graph to find which functions, classes, and modules are relevant to the current task, then injects only those into context. In practice this reduces token usage by 60–80% on large codebases compared to naively dumping files.

**Privacy and offline capability.** The default LLM provider is Ollama, which runs entirely on your machine. Your source code never leaves your network unless you explicitly configure a cloud provider. Cloud APIs (Anthropic, OpenAI, Gemini, Groq) are opt-in for tasks where you want higher model capability.

**Multi-step task execution.** Implementing a feature typically involves reading several files to understand context, writing or editing code, running tests, fixing failures, and sometimes making follow-up edits. DevAgent handles this as a single continuous session with persistent memory, rather than requiring you to manually copy-paste context between steps.

---

## How it works

DevAgent uses a ReAct (Reason + Act) loop. On each turn the LLM decides what to do next — read a file, run a shell command, edit a module, call the GitHub API — executes that action using a tool, and incorporates the result before deciding the next step. This continues until the task is complete or a final answer is reached.

The loop is driven by a set of built-in tools: file reading and writing, shell execution, git operations, grep and search, GitHub API calls, and CodePrism graph queries. You can extend it with custom tools through the plugin registry (see [Writing plugin tools](#writing-plugin-tools)).

Sessions are persisted in a local SQLite database. You can close the terminal, return later, and resume exactly where you left off. Token usage and estimated cost are tracked per session and displayed live.

---

## Supported LLM providers

| Provider | Models | Offline | Best for |
|---|---|---|---|
| **Ollama** (default) | qwen2.5-coder:7b, llama3.2, deepseek-coder, any pulled model | Yes | Privacy-sensitive projects; day-to-day use |
| **Ollama Cloud** | gpt-oss:20b, nemotron-3-nano:30b, gemma4:31b, and 15+ hosted models | No | Higher capability without switching provider APIs |
| **Anthropic** | claude-sonnet-4-6, claude-opus-4-8, claude-haiku-4-5 | No | Complex reasoning, long-context tasks |
| **OpenAI** | gpt-4o, gpt-4o-mini, o1, o3-mini | No | General coding, broad language support |
| **Google Gemini** | gemini-1.5-pro, gemini-2.0-flash | No | Long context windows, multi-modal tasks |
| **Groq** | llama-3.3-70b-versatile, llama-3.1-8b-instant | No | Fast inference on open-weight models |

All providers use their official Python SDKs. There is no LangChain or LangGraph dependency.

**Multi-model routing.** You can assign different providers and models to different task types. For example, use a small local model for file reads and a stronger cloud model only when the agent is writing or reviewing code. See [Configuration](#configuration) for the router setup.

---

## Installation

Install with `pipx` to keep dependencies isolated from your system Python:

```bash
pipx install devagent
```

Or install into a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install devagent
```

**Python requirement:** 3.12 or 3.13.

**Optional — Ollama:** Required for offline use. Download from [ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull qwen2.5-coder:7b
```

**Optional — Node.js:** Required only if you enable the GitHub MCP server integration. Download from [nodejs.org](https://nodejs.org).

**Optional — CodePrism:** The knowledge graph integration. Install separately if not already pulled as a dependency:

```bash
pip install codeprism-ai
```

---

## Quick start

```bash
# Step 1: run the setup wizard
devagent init
```

The wizard prompts for your LLM provider and optionally a GitHub token. All settings are written to a TOML config file — you can edit it directly at any time.

```bash
# Step 2: go to your project root and index the codebase
cd /path/to/your/project
devagent index
```

Indexing builds the CodePrism knowledge graph from your source files. It takes a few seconds for small projects and a couple of minutes for large ones. Run it again after significant code changes; it performs an incremental update automatically.

```bash
# Step 3: start an interactive session
devagent
```

You now have an interactive session. Type any task in plain language:

```
> explain what src/auth/middleware.py does
> add rate limiting to the login endpoint
> run the tests for the auth module and fix any failures
> implement issue #47 from our GitHub repository
```

The agent works through the task step by step, showing its reasoning and the results of each tool call. When it finishes, you can review the changes in your editor and continue or close the session.

**Resuming a session:**

```bash
devagent session list
devagent session resume <session-id>
```

---

## Integrations

DevAgent pairs well with every major AI tool and editor. See **[INTEGRATIONS.md](INTEGRATIONS.md)** for full setup guides covering:

- **Claude and Claude Code** — use Claude as the reasoning engine, or run alongside Claude Code for complementary workflows
- **ChatGPT / OpenAI Codex** — route DevAgent through GPT-4o or o1; use ChatGPT for design decisions and DevAgent for execution
- **Antigravity** — terminal integration + MCP server for CodePrism graph access
- **GitHub Copilot** — Copilot handles inline completion; DevAgent handles multi-step implementation
- **Cursor, Windsurf, VS Code, JetBrains, Zed** — run DevAgent in the integrated terminal alongside any editor AI

---

## Benchmarks

DevAgent ships with a 20-task benchmark covering bug fixes, feature adds, refactors, test writing, security audits, and onboarding tasks. Each task runs the full agent loop and passes only if a `pytest` or assertion oracle exits 0.

| Model | Provider | Pass rate |
|---|---|---|
| llama3.2:3b | Ollama (local) | 9/20 (45%) |
| **gpt-oss:20b** | **Ollama Cloud** | **20/20 (100%)** |

See **[BENCHMARKS.md](BENCHMARKS.md)** for per-task results, failure analysis, and instructions for running the benchmark against any supported model.

```bash
# Run against any model
devagent bench native --live --model gpt-oss:20b --provider ollama
```

---

## Commands reference

### Core

| Command | Description |
|---|---|
| `devagent` | Start an interactive session in the current directory |
| `devagent init` | Run the setup wizard (LLM provider, GitHub token, search) |
| `devagent doctor` | Check provider connectivity, index status, offline capability |
| `devagent config --show` | Print current configuration |
| `devagent config --set key=value` | Set a configuration value |

### Codebase indexing

| Command | Description |
|---|---|
| `devagent index` | Build or update the CodePrism knowledge graph |
| `devagent index --full` | Force a complete re-index (ignores incremental cache) |
| `devagent index --status` | Show index statistics without rebuilding |

### GitHub flows

| Command | Description |
|---|---|
| `devagent implement <issue-url>` | Implement a GitHub issue end-to-end |
| `devagent review <pr-url>` | Review a pull request and post inline comments |
| `devagent triage <owner/repo>` | Triage open issues with labels and effort estimates |
| `devagent fix-ci <run-url>` | Analyse a failed CI run and push a fix |

### Sessions

| Command | Description |
|---|---|
| `devagent session list` | List all sessions with token usage and date |
| `devagent session resume <id>` | Resume a previous session |
| `devagent session delete <id>` | Delete a session and its history |

### Watcher

| Command | Description |
|---|---|
| `devagent watcher start <owner/repo>` | Start background monitoring of a repository |
| `devagent watcher status` | Show watcher state and recent analyses |
| `devagent watcher stop` | Stop the background watcher |

### Server

| Command | Description |
|---|---|
| `devagent serve` | Start the REST API server on port 7331 |
| `devagent serve --port 8080` | Start on a custom port |

---

## GitHub workflows

DevAgent treats GitHub as a first-class integration. All GitHub commands accept full issue or PR URLs, so you do not need to configure a default repository.

**Implement an issue:**

```bash
devagent implement https://github.com/owner/repo/issues/42
```

The agent fetches the issue description, analyses which parts of your codebase are affected using the code graph, writes the implementation, runs the relevant tests, and summarises what changed. You review and commit.

**Review a pull request:**

```bash
devagent review https://github.com/owner/repo/pull/17
```

The agent fetches the PR diff, checks the changed code against the repository's conventions, identifies potential bugs or missing test cases, and posts inline review comments via the GitHub API.

**Triage a backlog:**

```bash
devagent triage owner/repo
```

The agent reads all open issues, estimates effort (trivial / small / medium / large), suggests label assignments, and identifies which issues conflict with or depend on each other.

**Fix a failed CI run:**

```bash
devagent fix-ci https://github.com/owner/repo/actions/runs/12345
```

The agent fetches the CI log, identifies the failing step, reads the relevant source files, proposes and applies a fix, and runs the test locally to verify before you push.

**Requirement:** A GitHub Personal Access Token with `repo` scope. Set it once:

```bash
devagent config --set github.token=ghp_...
```

---

## Configuration

DevAgent stores configuration in TOML format:

- **Linux / macOS:** `~/.config/devagent/config.toml`
- **Windows:** `%APPDATA%\devagent\config.toml`

**LLM provider:**

```toml
[llm]
provider = "ollama"            # ollama | anthropic | openai | gemini | groq
model    = "qwen2.5-coder:7b"
base_url = "http://localhost:11434"   # Ollama only; omit for cloud providers
```

**Multi-model router:**

Use different providers for different stages of a task. The agent automatically selects the appropriate model based on what it is doing.

```toml
[router]
planning  = { provider = "anthropic", model = "claude-sonnet-4-6" }
coding    = { provider = "ollama",    model = "qwen2.5-coder:7b" }
reviewing = { provider = "anthropic", model = "claude-haiku-4-5-20251001" }
cheap     = { provider = "ollama",    model = "qwen2.5-coder:7b" }
fallback  = { provider = "ollama",    model = "qwen2.5-coder:7b" }
```

**GitHub:**

```toml
[github]
token        = "ghp_..."
default_repo = "owner/repo"    # optional; used when no repo is specified
```

**Token budget:**

```toml
[session]
max_tokens  = 200000    # hard stop; agent halts if this is reached
warn_at_pct = 80        # warn when 80% of budget is consumed
```

**Setting values from the CLI:**

```bash
devagent config --set llm.provider=anthropic
devagent config --set llm.model=claude-sonnet-4-6
devagent config --set session.max_tokens=100000
```

---

## Session management

Sessions persist between terminal restarts. Every message, tool call, and result is stored in a local SQLite database. Token usage is tracked per model and converted to USD cost using built-in rate tables.

```bash
devagent session list
```

```
ID          Title                          Model                  Updated
a1b2c3d4    Implement rate limiting        ollama/qwen2.5-coder   2026-08-21 14:32
e5f6a7b8    Review PR #17                  anthropic/sonnet-4.6   2026-08-20 09:15
```

```bash
devagent session resume a1b2c3d4
```

Resuming restores the full message history and memory block. The agent has access to everything it said and did in the previous session.

**Session memory** is a separate key-value store you can read and write during a session:

```
> remember that the payment module uses Stripe's v3 API
> what do you know about the payment module?
```

Memory entries persist across resumes and are injected into every LLM call as a compact block (~200 tokens), so the agent always has the key facts without replaying the entire history.

---

## Security gate

Every file write passes through a security scanner before hitting disk. The gate has two levels:

**Block** — write is rejected and an error is returned to the agent:

- Hardcoded secrets or API keys in source files
- `eval(user_input)` or `exec(user_controlled_string)` patterns
- Path traversal attempts (`../../etc/passwd`)
- `subprocess.run(user_input, shell=True)` with untrusted input
- Known CVE patterns (configurable)

**Warn** — write proceeds only after confirmation:

- `chmod 777` on sensitive paths
- `curl | bash` or equivalent install-from-internet patterns
- Disabling authentication or rate limiting via code comments
- Development keys or test credentials that look real

Security events are logged per session. Run `devagent session list` and inspect a session to see its security summary.

---

## Background watcher

The watcher monitors a GitHub repository in the background and automatically analyses new issues as they are opened:

```bash
devagent watcher start owner/repo
```

For each new issue the watcher estimates complexity, identifies which files are likely affected, and stores the analysis locally. You can review analyses in your next interactive session or from the CLI:

```bash
devagent watcher status
```

The watcher runs as a background process and survives terminal restarts. Stop it explicitly when you no longer need it:

```bash
devagent watcher stop
```

---

## REST API

Run `devagent serve` to expose a local API that editor extensions, browser tools, or scripts can call:

```bash
devagent serve                 # http://localhost:7331
devagent serve --port 8080     # custom port
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check; returns version |
| GET | `/api/status` | LLM config, index status, offline capability |
| GET | `/api/sessions` | Last 20 sessions with metadata |
| GET | `/api/sessions/<id>` | Full session detail and token totals |
| GET | `/api/tools` | All registered tools with descriptions |
| GET | `/api/graph/stats` | CodePrism graph statistics |
| GET | `/api/graph/files` | File map from the knowledge graph |

All responses are JSON. CORS is enabled for local development. No authentication is applied — bind to `127.0.0.1` (the default) to avoid exposing the API on your network.

---

## Writing plugin tools

You can extend the agent with custom tools by registering them in the `ToolRegistry`. Tools are plain Python callables; they do not need to live inside the DevAgent package.

```python
from devagent.tools.registry import ToolRegistry

def search_internal_docs(args: dict) -> str:
    query = args.get("query", "")
    # your search logic here
    return f"Results for '{query}': ..."

def register(registry: ToolRegistry) -> None:
    registry.register(
        name="search_internal_docs",
        description=(
            "Search the company's internal documentation. "
            "Use this when the user asks about internal APIs or processes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        },
        handler=search_internal_docs,
    )
```

**Tool conventions:**

- Always return a `str`. Never raise an exception; return `"[error] ..."` instead.
- Keep descriptions precise — the LLM uses them to decide when to call the tool.
- Avoid side effects that cannot be undone without user confirmation.

See [docs/plugin_tools.md](docs/plugin_tools.md) for the full guide including security wrapping, parameter tips, and examples of the 29 built-in tools.

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide, including code style, test requirements, and the PR process.

**Quick summary:**

```bash
# Clone and install
git clone https://github.com/yourusername/DevAgent.git
cd DevAgent
pip install -e ".[dev]"

# Run tests
python -m pytest tests/

# Run the linter (zero errors required for CI)
ruff check devagent/ tests/

# Open a PR
git checkout -b feat/your-feature
# ... make changes and add tests ...
git push origin feat/your-feature
```

**CI runs automatically on every PR:**

- Lint with `ruff` on Python 3.12
- Tests on Python 3.12 and 3.13
- Wheel build

PyPI publish is triggered by creating a GitHub Release. There are no stored secrets — publish uses OIDC Trusted Publishing.

For bug reports, use the bug report issue template. For feature ideas, use the feature request template. Both are available when opening a new issue on GitHub.

---

## License

MIT. See [LICENSE](LICENSE) for details.

---

<div align="center">
<sub>Built with Python 3.12+. No LangGraph. No mandatory cloud. Your code stays yours.</sub>
</div>
