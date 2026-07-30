# SpecSync

**Requirements-to-code gap analysis for developers.**

SpecSync is a local, terminal-based CLI tool that bridges the gap between your project specifications (GitHub issues, Markdown specs, or plain text) and your actual codebase. Powered by local LLMs (via Ollama) and the Model Context Protocol (MCP), SpecSync parses your requirements, semantically searches your codebase, and generates a comprehensive gap report detailing what exists, what needs extending, and what is completely missing.

---

## 🌟 Features

- **Automated Gap Analysis**: Compares a spec against your existing codebase and categorizes requirements into:
  - ✅ **Reuse**: Code already exists.
  - ⚠️ **Extend**: Code exists but needs modification.
  - ❌ **Conflict**: Requirement contradicts existing logic.
  - 🔨 **Net New**: Entirely new implementation required.
- **Local & Private**: Fully supports running locally via Ollama and local ChromaDB embeddings. Your code never has to leave your machine.
- **Model Context Protocol (MCP)**: Leverages official MCP servers to safely read your filesystem and fetch GitHub issues, alongside custom Python MCP servers for AST parsing and semantic search.
- **Effort Estimation & Planning**: Uses heuristic baselines and LLM reasoning to estimate implementation hours and suggest an optimal implementation order.
- **Beautiful Output**: Renders beautiful Rich terminal UI interfaces and persists detailed Markdown reports.

---

## 🚀 Installation

SpecSync is a Python CLI tool. The recommended way to install it is via `pipx` to keep its dependencies isolated:

```bash
pipx install specsync
```

*(Alternatively, you can install it globally or in a virtual environment using `pip install specsync`)*.

### ⚠️ System Requirements
Because SpecSync utilizes official Model Context Protocol (MCP) servers under the hood, you **must have Node.js installed** on your machine.
- [Download and install Node.js](https://nodejs.org/) (Ensure `npx` is available in your PATH).

---

## ⚙️ Configuration & Setup

Before analyzing your first project, initialize the global configuration:

```bash
specsync init
```
This interactive prompt will help you set up:
- **LLM Provider**: Choose between Ollama (local), Groq, Anthropic, OpenAI, or Gemini.
- **GitHub Token**: (Optional) Required if you want SpecSync to fetch specs directly from GitHub Issues.
- **Search Provider**: (Optional) Brave or SearchX for gathering web context on implementation patterns.

*You can always view or modify your config later using `specsync config --show` or `specsync config --set key=value`.*

---

## 🛠️ Usage

### 1. Index your Codebase
Navigate to your project directory and build the semantic search index. This uses local AST parsing (for Python) and text chunking to embed your codebase into a local ChromaDB instance.

```bash
cd /path/to/your/project
specsync index
```
*Note: SpecSync respects your `.gitignore` files automatically. Re-running this command performs an incremental index (only updating changed files).*

### 2. Analyze a Specification
Run a gap analysis against your codebase using a GitHub Issue, a local Markdown file, or inline text:

```bash
# Analyze a GitHub Issue (requires GitHub Token in config)
specsync analyze --issue 142 --repo owner/my-repo

# Analyze a local spec file
specsync analyze --spec ./docs/new_feature.md

# Analyze inline text
specsync analyze --text "Add a new user authentication endpoint supporting OAuth2."
```

By default, this outputs a beautiful Rich terminal report **and** saves a `.md` markdown report in your local app data directory.

### 3. Manage Reports
View previously generated reports for the current project:

```bash
# List all saved reports
specsync reports

# View a specific report in the terminal
specsync reports --show issue-142
```

### 4. Semantic Search
Need to quickly find where something is implemented? Use the standalone semantic search:

```bash
specsync search "user authentication logic"
```

---

## 🩺 Troubleshooting

If you run into issues with dependencies or services, run the built-in doctor command to check the health of your environment:

```bash
specsync doctor
```

## 📝 License
MIT License.
