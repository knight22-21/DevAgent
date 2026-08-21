<div align="center">

# DevAgent

**An AI coding agent for your terminal. Offline-first, GitHub-native, token-efficient.**

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
- [Using DevAgent with AI tools](#using-devagent-with-ai-tools)
  - [Claude and Claude Code](#claude-and-claude-code)
  - [ChatGPT and OpenAI Codex](#chatgpt-and-openai-codex)
  - [Antigravity](#antigravity)
  - [GitHub Copilot](#github-copilot)
  - [Cursor](#cursor)
  - [Windsurf](#windsurf)
  - [VS Code](#vs-code)
  - [JetBrains IDEs](#jetbrains-ides)
  - [Zed](#zed)
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

## Using DevAgent with AI tools

DevAgent is a command-line agent, not a chat interface. It pairs well with every major AI tool because it fills the role none of them fill: local, multi-step code execution with persistent context. Below is a guide for each environment.

---

### Claude and Claude Code

**Using Claude as DevAgent's reasoning engine**

Set Anthropic as your provider and pick a model:

```bash
devagent config --set llm.provider=anthropic
devagent config --set llm.model=claude-sonnet-4-6
```

Or set the environment variable and skip storing the key in config:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
devagent config --set llm.provider=anthropic
```

Claude Sonnet 4.6 is a strong default for coding tasks. Claude Opus 4.8 gives deeper reasoning for complex refactors or architectural decisions at higher cost.

**Using DevAgent alongside Claude Code**

Claude Code and DevAgent serve different but complementary roles. Claude Code is tightly integrated with the Anthropic API and is excellent for conversational code exploration and quick edits. DevAgent adds persistent sessions, offline Ollama support, GitHub automation, and the CodePrism knowledge graph.

A practical way to combine them: use Claude Code for exploratory questions and quick changes, and invoke DevAgent for longer tasks like implementing a full feature or triaging a backlog of issues.

Run both in separate terminal tabs or panes in your editor. They operate on the same working directory, so changes from one are immediately visible to the other.

**Connecting CodePrism to Claude Desktop via MCP**

If you use Claude Desktop, you can expose your codebase's knowledge graph as an MCP server:

```bash
devagent serve
```

This starts a local server at `http://localhost:7331` with endpoints for graph stats, file maps, and session state. You can point Claude Desktop's MCP configuration at this endpoint to give Claude read access to the structured graph of your codebase without pasting raw files into the conversation.

---

### ChatGPT and OpenAI Codex

**Using GPT as DevAgent's reasoning engine**

```bash
devagent config --set llm.provider=openai
devagent config --set llm.model=gpt-4o
```

Or with an environment variable:

```bash
export OPENAI_API_KEY=sk-...
devagent config --set llm.provider=openai
```

Available models: `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini`. The `gpt-4o-mini` model is a cost-effective choice for most coding tasks. Use `o1` or `o3-mini` for problems that benefit from extended reasoning.

**What DevAgent adds to a ChatGPT workflow**

ChatGPT is a browser-based chat interface. It can reason about code you paste in, but it cannot read your files, run commands, or push commits. DevAgent handles the execution layer that ChatGPT cannot.

A practical split: use ChatGPT to think through design decisions and explore approaches, then translate the outcome into a DevAgent task that actually implements it:

```bash
# After deciding on the approach in ChatGPT:
devagent
> implement the OAuth2 flow we discussed — start with the callback handler in src/auth/
```

**OpenAI Codex**

OpenAI Codex refers to the model that powers GitHub Copilot and the Codex API. If you are calling the Codex API directly, you can route DevAgent through it by setting `provider=openai` and specifying the appropriate model endpoint. For GitHub Copilot (the editor extension), see [GitHub Copilot](#github-copilot) below.

---

### Antigravity

Antigravity is an AI-first development environment. DevAgent integrates with it at two levels.

**Terminal integration**

Antigravity includes an integrated terminal. Run `devagent` inside it to start an agent session. The agent's file edits are immediately reflected in Antigravity's editor pane and version control view.

**MCP integration**

Antigravity supports Model Context Protocol. Start the DevAgent REST server:

```bash
devagent serve --port 7331
```

Add it as an MCP source in Antigravity's settings under **Integrations > MCP Servers**:

```
http://localhost:7331
```

This gives Antigravity's AI access to your CodePrism knowledge graph — the structured map of your codebase — without any file content leaving your machine. Antigravity's AI can then reference graph-level facts (what modules exist, what a function's callers are, which files are affected by a change) when answering your questions.

**Using Ollama through Antigravity**

If Antigravity is configured to route through a local Ollama instance, DevAgent can share the same Ollama service. Both tools connect to `http://localhost:11434` by default, so no additional setup is needed.

**Recommended workflow with Antigravity**

1. Use Antigravity's inline AI for code completion and quick questions.
2. When you need multi-step execution — implementing an issue, running and fixing tests, generating a PR description — switch to the DevAgent session in the terminal panel.
3. Antigravity's diff view shows the agent's changes as they land, so you can review and steer without leaving the editor.

---

### GitHub Copilot

GitHub Copilot provides inline code completion within your editor. DevAgent and Copilot operate at different levels and work well together.

Copilot suggests the next line or block as you type. DevAgent takes a natural-language description and executes a multi-step plan: reading relevant files, writing changes across multiple modules, running tests, and verifying the result. They do not conflict.

**Typical combined workflow:**

1. Open a GitHub issue in your browser.
2. Run `devagent implement <issue-url>` in your editor's integrated terminal.
3. DevAgent scaffolds the implementation — creates files, writes boilerplate, adds test cases.
4. Switch to your editor. Copilot helps you fill in implementation details as you refine the scaffolded code.
5. Return to the DevAgent session to run the full test suite and fix any remaining failures.

**Note on Copilot Chat:** Copilot Chat (available in VS Code and JetBrains) can answer questions about your codebase but does not execute commands or make file edits on its own. DevAgent handles the execution side.

---

### Cursor

Cursor is an AI editor with Claude built in. DevAgent runs in Cursor's integrated terminal and complements Cursor's inline AI.

**Setup:**

1. Open your project in Cursor.
2. Open the terminal panel (`Ctrl+` ` ` or `Cmd+` ` `).
3. Run `devagent` to start a session.

Cursor's AI Chat is best for questions, explanations, and small edits. DevAgent handles tasks that span multiple files, require test execution, or involve GitHub operations.

**Sharing context with Cursor**

Cursor indexes your codebase for its own embeddings. DevAgent's CodePrism graph is a complementary but separate index — it stores AST-level facts (function signatures, call graphs, import trees) rather than semantic embeddings. You can use both simultaneously; they do not interfere with each other.

**Using Claude models in DevAgent while working in Cursor**

Since Cursor uses Anthropic models internally and DevAgent can also call Anthropic's API, you are making two separate sets of API calls. If you want to reduce API spend, consider pointing DevAgent at a local Ollama model for background tasks and reserving the Anthropic API for Cursor's inline AI. Configure via:

```bash
devagent config --set llm.provider=ollama
devagent config --set llm.model=qwen2.5-coder:7b
```

---

### Windsurf

Windsurf (by Codeium) is an AI-native editor. DevAgent integrates the same way as Cursor — via the integrated terminal.

**Setup:**

1. Open your project in Windsurf.
2. Open the terminal (`Ctrl+` ` ` `).
3. Run `devagent index` once to build the knowledge graph, then `devagent` to start a session.

Windsurf's Cascade feature handles multi-step code changes within the editor itself. DevAgent complements it for tasks that go beyond file editing: running shell commands, calling GitHub APIs, managing sessions across terminal restarts, or using local Ollama models instead of Codeium's cloud.

---

### VS Code

VS Code users typically use one or more AI extensions: GitHub Copilot, Continue, or CodeGPT. DevAgent works alongside all of them.

**Setup:**

1. Open the integrated terminal in VS Code (`Ctrl+` ` ` `).
2. Run `devagent init` if you have not set up a provider yet.
3. Run `devagent index` in your project root.
4. Run `devagent` to start a session.

**Using with the Continue extension**

[Continue](https://continue.dev/) is an open-source VS Code extension that supports local models. If you have Continue configured with Ollama, you can share the Ollama instance with DevAgent:

```bash
devagent config --set llm.provider=ollama
devagent config --set llm.model=<model-you-pulled>
```

Both Continue and DevAgent will route through the same local Ollama service. Continue handles inline suggestions inside VS Code; DevAgent handles multi-step tasks in the terminal.

---

### JetBrains IDEs

DevAgent works in IntelliJ IDEA, PyCharm, WebStorm, GoLand, and other JetBrains IDEs through the built-in terminal.

**Setup:**

1. Open the terminal pane (`Alt+F12` on Windows/Linux, `Option+F12` on macOS).
2. Run `devagent` in your project directory.

JetBrains AI Assistant handles inline completions and chat. DevAgent handles longer-running tasks in the terminal. Changes DevAgent writes to disk are picked up by IntelliJ's file watcher and appear in the IDE immediately, including in the VCS diff view.

---

### Zed

Zed is a high-performance editor with AI features. Run DevAgent in Zed's integrated terminal:

1. Open the terminal with `Ctrl+` ` ` ` (or via the menu).
2. Run `devagent` from your project root.

Zed's AI panel can answer code questions. DevAgent handles execution. The split is the same as with every other editor: use the editor AI for exploration, use DevAgent when you need the agent to actually run commands and make changes.

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
