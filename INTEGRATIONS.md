# Using DevAgent with AI Tools

DevAgent is a command-line agent, not a chat interface. It pairs well with every major AI tool because it fills the role none of them fill: local, multi-step code execution with persistent context. Below is a setup guide for each environment.

---

## Contents

- [Claude and Claude Code](#claude-and-claude-code)
- [ChatGPT and OpenAI Codex](#chatgpt-and-openai-codex)
- [Antigravity](#antigravity)
- [GitHub Copilot](#github-copilot)
- [Cursor](#cursor)
- [Windsurf](#windsurf)
- [VS Code](#vs-code)
- [JetBrains IDEs](#jetbrains-ides)
- [Zed](#zed)

---

## Claude and Claude Code

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

## ChatGPT and OpenAI Codex

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

## Antigravity

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

## GitHub Copilot

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

## Cursor

Cursor is an AI editor with Claude built in. DevAgent runs in Cursor's integrated terminal and complements Cursor's inline AI.

**Setup:**

1. Open your project in Cursor.
2. Open the terminal panel (`` Ctrl+` `` or `` Cmd+` ``).
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

## Windsurf

Windsurf (by Codeium) is an AI-native editor. DevAgent integrates the same way as Cursor — via the integrated terminal.

**Setup:**

1. Open your project in Windsurf.
2. Open the terminal (`` Ctrl+` ``).
3. Run `devagent index` once to build the knowledge graph, then `devagent` to start a session.

Windsurf's Cascade feature handles multi-step code changes within the editor itself. DevAgent complements it for tasks that go beyond file editing: running shell commands, calling GitHub APIs, managing sessions across terminal restarts, or using local Ollama models instead of Codeium's cloud.

---

## VS Code

VS Code users typically use one or more AI extensions: GitHub Copilot, Continue, or CodeGPT. DevAgent works alongside all of them.

**Setup:**

1. Open the integrated terminal in VS Code (`` Ctrl+` ``).
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

## JetBrains IDEs

DevAgent works in IntelliJ IDEA, PyCharm, WebStorm, GoLand, and other JetBrains IDEs through the built-in terminal.

**Setup:**

1. Open the terminal pane (`Alt+F12` on Windows/Linux, `Option+F12` on macOS).
2. Run `devagent` in your project directory.

JetBrains AI Assistant handles inline completions and chat. DevAgent handles longer-running tasks in the terminal. Changes DevAgent writes to disk are picked up by IntelliJ's file watcher and appear in the IDE immediately, including in the VCS diff view.

---

## Zed

Zed is a high-performance editor with AI features. Run DevAgent in Zed's integrated terminal:

1. Open the terminal with `` Ctrl+` `` (or via the menu).
2. Run `devagent` from your project root.

Zed's AI panel can answer code questions. DevAgent handles execution. The split is the same as with every other editor: use the editor AI for exploration, use DevAgent when you need the agent to actually run commands and make changes.
