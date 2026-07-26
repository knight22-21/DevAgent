"""SpecSync CLI — all command definitions using Typer + Rich."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from specsync.core.config import (
    BraveConfig,
    GitHubConfig,
    LLMConfig,
    LLMFallbackConfig,
    OutputConfig,
    SearchXConfig,
    SpecSyncConfig,
    config_exists,
    load_config,
    save_config,
)
from specsync.core.storage import get_config_path

app = typer.Typer(
    name="specsync",
    help="SpecSync — Requirements-to-code gap analysis for developers.",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()

# ---------------------------------------------------------------------------
# Provider defaults
# ---------------------------------------------------------------------------
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama": {"model": "qwen2.5-coder:7b", "base_url": "http://localhost:11434"},
    "groq": {"model": "llama-3.3-70b-versatile"},
    "anthropic": {"model": "claude-3-5-haiku-20241022"},
    "openai": {"model": "gpt-4o-mini"},
    "gemini": {"model": "gemini-1.5-flash"},
}

PROVIDER_KEY_ENV: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask_key(key: str) -> str:
    """Mask an API key, showing only the last 4 characters."""
    if not key or len(key) <= 4:
        return key
    return "*" * (len(key) - 4) + key[-4:]


def _validate_ollama(base_url: str, model: str) -> tuple[bool, str]:
    """Validate Ollama is running and the model is available."""
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        available = [m.get("name", "") for m in data.get("models", [])]
        # Check if the requested model is available (may include :latest suffix)
        for m in available:
            if m == model or m.startswith(f"{model}:") or model.startswith(m.split(":")[0]):
                return True, f"Model '{model}' available on Ollama"
        # Model not found but Ollama is running
        names = ", ".join(available[:5]) if available else "none"
        return False, (
            f"Ollama is running but model '{model}' not found. "
            f"Available: {names}. Pull it with: ollama pull {model}"
        )
    except httpx.ConnectError:
        return False, (
            f"Ollama is not reachable at {base_url}. "
            "Start it with: ollama serve"
        )
    except Exception as exc:
        return False, f"Ollama check failed: {exc}"


def _validate_github_token(token: str) -> tuple[bool, str]:
    """Validate a GitHub personal access token."""
    if not token:
        return False, "No token configured"
    try:
        resp = httpx.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            username = resp.json().get("login", "unknown")
            return True, f"Authenticated as {username}"
        return False, f"GitHub returned status {resp.status_code}"
    except Exception as exc:
        return False, f"GitHub check failed: {exc}"


def _validate_brave_key(api_key: str) -> tuple[bool, str]:
    """Validate a Brave Search API key."""
    if not api_key:
        return False, "Not configured (optional)"
    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": "test", "count": 1},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "API key valid"
        return False, f"Brave returned status {resp.status_code}"
    except Exception as exc:
        return False, f"Brave check failed: {exc}"


def _validate_searchx_key(api_key: str) -> tuple[bool, str]:
    """Validate a SearchX API key."""
    if not api_key:
        return False, "Not configured (optional)"
    try:
        resp = httpx.get(
            "https://searchx.dev/api/v1/search",
            params={"q": "test", "count": 1},
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "API key valid"
        return False, f"SearchX returned status {resp.status_code}"
    except Exception as exc:
        return False, f"SearchX check failed: {exc}"


def _check_command(cmd: list[str]) -> tuple[bool, str]:
    """Check if a command is available and return its version."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, shell=True
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return True, version
        return False, f"Command returned exit code {result.returncode}"
    except FileNotFoundError:
        return False, "Not found in PATH"
    except Exception as exc:
        return False, str(exc)


# ============================
# COMMANDS
# ============================


@app.command()
def init() -> None:
    """Interactive first-time setup — configure LLM provider, API keys, and preferences."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to SpecSync![/bold cyan]\n\n"
            "This wizard will configure your LLM provider, API keys, and preferences.\n"
            "All settings are stored in your user config directory.",
            title="⚡ SpecSync Setup",
            border_style="cyan",
        )
    )
    console.print()

    # Load existing config if present
    existing = load_config() if config_exists() else None
    if existing:
        console.print(
            "[yellow]An existing configuration was found. "
            "Current values will be shown as defaults.[/yellow]\n"
        )

    # --- Step 1: LLM provider ---
    console.print("[bold]Step 1:[/bold] Choose your LLM provider\n")
    providers = ["ollama", "groq", "anthropic", "openai", "gemini"]
    for i, p in enumerate(providers, 1):
        default_tag = " [dim](default, local, free)[/dim]" if p == "ollama" else ""
        console.print(f"  {i}. {p}{default_tag}")
    console.print()

    default_choice = "1"
    if existing:
        try:
            default_choice = str(providers.index(existing.llm.provider) + 1)
        except ValueError:
            pass

    choice = Prompt.ask(
        "Select provider",
        choices=["1", "2", "3", "4", "5"],
        default=default_choice,
    )
    provider = providers[int(choice) - 1]

    # --- Step 2: Model name ---
    default_model = PROVIDER_DEFAULTS[provider]["model"]
    if existing and existing.llm.provider == provider:
        default_model = existing.llm.model or default_model

    model = Prompt.ask("Model name", default=default_model)

    # --- Step 3: Provider-specific config ---
    base_url = ""
    api_key = ""

    if provider == "ollama":
        default_url = PROVIDER_DEFAULTS["ollama"]["base_url"]
        if existing and existing.llm.base_url:
            default_url = existing.llm.base_url
        base_url = Prompt.ask("Ollama base URL", default=default_url)
    else:
        existing_key = existing.llm.api_key if existing else ""
        if existing_key:
            console.print(f"  Current API key: {_mask_key(existing_key)}")
        api_key = Prompt.ask(
            f"{provider.capitalize()} API key",
            password=True,
            default=existing_key if existing_key else "",
        )

    # --- Step 4: GitHub token ---
    console.print()
    console.print("[bold]Step 2:[/bold] GitHub Personal Access Token")
    console.print(
        "  [dim]Create one at: https://github.com/settings/tokens[/dim]"
    )

    existing_gh_token = existing.github.token if existing else ""
    if existing_gh_token:
        console.print(f"  Current token: {_mask_key(existing_gh_token)}")

    gh_token = Prompt.ask(
        "GitHub token",
        password=True,
        default=existing_gh_token if existing_gh_token else "",
    )

    # --- Step 5: Search provider selection ---
    console.print()
    console.print("[bold]Step 3:[/bold] Choose your search provider")
    console.print("  [dim]SearchX is free (3K/day), Brave is paid[/dim]")
    
    search_providers = ["searchx", "brave"]
    for i, p in enumerate(search_providers, 1):
        default_tag = " [dim](default, free)[/dim]" if p == "searchx" else ""
        console.print(f"  {i}. {p}{default_tag}")
    console.print()

    default_search_choice = "1"
    if existing:
        try:
            default_search_choice = str(search_providers.index(existing.search_provider) + 1)
        except ValueError:
            pass

    search_choice = Prompt.ask(
        "Select search provider",
        choices=["1", "2"],
        default=default_search_choice,
    )
    search_provider = search_providers[int(search_choice) - 1]

    # --- Step 6: Search API key ---
    console.print()
    if search_provider == "brave":
        console.print("[bold]Step 4:[/bold] Brave Search API Key [dim](optional)[/dim]")
        console.print(
            "  [dim]Get one at: https://brave.com/search/api/[/dim]"
        )
        existing_key = existing.brave.api_key if existing else ""
        if existing_key:
            console.print(f"  Current key: {_mask_key(existing_key)}")
        
        search_key = ""
        if Confirm.ask("Configure Brave Search?", default=bool(existing_key)):
            search_key = Prompt.ask(
                "Brave API key",
                password=True,
                default=existing_key if existing_key else "",
            )
        brave_key = search_key
        searchx_key = existing.searchx.api_key if existing else ""
    else:
        console.print("[bold]Step 4:[/bold] SearchX API Key [dim](optional)[/dim]")
        console.print(
            "  [dim]Get one at: https://searchx.dev/ (3K/day free)[/dim]"
        )
        existing_key = existing.searchx.api_key if existing else ""
        if existing_key:
            console.print(f"  Current key: {_mask_key(existing_key)}")
        
        searchx_key = ""
        if Confirm.ask("Configure SearchX?", default=bool(existing_key)):
            searchx_key = Prompt.ask(
                "SearchX API key",
                password=True,
                default=existing_key if existing_key else "",
            )
        brave_key = existing.brave.api_key if existing else ""

    # --- Step 6: Validate LLM provider ---
    console.print()
    with console.status("[cyan]Validating LLM provider...[/cyan]"):
        if provider == "ollama":
            ok, msg = _validate_ollama(base_url, model)
        else:
            # For cloud providers, just check that the key is non-empty
            ok = bool(api_key)
            msg = "API key provided" if ok else "No API key provided"

    if ok:
        console.print(f"  ✅ LLM provider: {msg}")
    else:
        console.print(f"  ❌ LLM provider: {msg}")
        if not Confirm.ask("Continue anyway?", default=False):
            raise typer.Exit(1)

    # --- Step 7: Validate search provider ---
    if search_provider == "brave" and brave_key:
        with console.status("[cyan]Validating Brave Search...[/cyan]"):
            ok, msg = _validate_brave_key(brave_key)
        if ok:
            console.print(f"  ✅ Brave Search: {msg}")
        else:
            console.print(f"  ❌ Brave Search: {msg}")
    elif search_provider == "searchx" and searchx_key:
        with console.status("[cyan]Validating SearchX...[/cyan]"):
            ok, msg = _validate_searchx_key(searchx_key)
        if ok:
            console.print(f"  ✅ SearchX: {msg}")
        else:
            console.print(f"  ❌ SearchX: {msg}")
    else:
        console.print(f"  ⚠️  {search_provider.capitalize()} API key not provided — search will not work")

    # --- Step 8: Validate GitHub token ---
    if gh_token:
        with console.status("[cyan]Validating GitHub token...[/cyan]"):
            ok, msg = _validate_github_token(gh_token)
        if ok:
            console.print(f"  ✅ GitHub: {msg}")
        else:
            console.print(f"  ❌ GitHub: {msg}")
    else:
        console.print("  ⚠️  GitHub token not provided — issue fetching will not work")

    # --- Step 9: Build and save config ---
    config = SpecSyncConfig(
        llm=LLMConfig(
            provider=provider,
            model=model,
            base_url=base_url or "http://localhost:11434",
            temperature=0.1,
            api_key=api_key,
            fallback=existing.llm.fallback if existing else None,
        ),
        github=GitHubConfig(
            token=gh_token,
            default_repo=existing.github.default_repo if existing else "",
        ),
        brave=BraveConfig(api_key=brave_key),
        searchx=SearchXConfig(api_key=searchx_key),
        search_provider=search_provider,
        output=OutputConfig(
            verbosity=existing.output.verbosity if existing else "normal",
        ),
    )

    save_config(config)

    console.print()
    console.print(
        Panel(
            f"[green bold]Configuration saved![/green bold]\n\n"
            f"Config file: [dim]{get_config_path()}[/dim]\n"
            f"Provider: [cyan]{provider}[/cyan]\n"
            f"Model: [cyan]{model}[/cyan]",
            title="✅ Setup Complete",
            border_style="green",
        )
    )


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Display current configuration"),
    set_value: Optional[str] = typer.Option(
        None, "--set", help="Update a config value (key=value, supports dot notation)"
    ),
) -> None:
    """Show or update SpecSync configuration."""
    if not show and set_value is None:
        console.print("[yellow]Use --show to display config or --set key=value to update.[/yellow]")
        raise typer.Exit()

    if show:
        if not config_exists():
            console.print(
                Panel(
                    "No configuration found. Run [bold cyan]specsync init[/bold cyan] first.",
                    title="❌ No Config",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

        cfg = load_config()
        table = Table(title="SpecSync Configuration", border_style="cyan")
        table.add_column("Setting", style="bold")
        table.add_column("Value")

        table.add_row("llm.provider", cfg.llm.provider)
        table.add_row("llm.model", cfg.llm.model)
        table.add_row("llm.base_url", cfg.llm.base_url)
        table.add_row("llm.temperature", str(cfg.llm.temperature))
        table.add_row("llm.api_key", _mask_key(cfg.llm.api_key) if cfg.llm.api_key else "")
        if cfg.llm.fallback:
            table.add_row("llm.fallback.provider", cfg.llm.fallback.provider)
            table.add_row("llm.fallback.model", cfg.llm.fallback.model)
        table.add_row("github.token", _mask_key(cfg.github.token) if cfg.github.token else "")
        table.add_row("github.default_repo", cfg.github.default_repo or "")
        table.add_row("search_provider", cfg.search_provider)
        table.add_row("brave.api_key", _mask_key(cfg.brave.api_key) if cfg.brave.api_key else "")
        table.add_row("searchx.api_key", _mask_key(cfg.searchx.api_key) if cfg.searchx.api_key else "")
        table.add_row("output.verbosity", cfg.output.verbosity)

        console.print()
        console.print(table)
        console.print(f"\n[dim]Config file: {get_config_path()}[/dim]")
        return

    if set_value:
        if "=" not in set_value:
            console.print("[red]Invalid format. Use: --set key=value[/red]")
            raise typer.Exit(1)

        key, value = set_value.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not config_exists():
            console.print(
                "[red]No configuration found. Run [bold]specsync init[/bold] first.[/red]"
            )
            raise typer.Exit(1)

        cfg = load_config()

        # Support dot notation for setting nested values
        parts = key.split(".")
        obj = cfg
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                console.print(f"[red]Unknown config key: {key}[/red]")
                raise typer.Exit(1)

        final_key = parts[-1]
        if not hasattr(obj, final_key):
            console.print(f"[red]Unknown config key: {key}[/red]")
            raise typer.Exit(1)

        # Type coercion
        current = getattr(obj, final_key)
        if isinstance(current, float):
            value = float(value)  # type: ignore[assignment]
        elif isinstance(current, int):
            value = int(value)  # type: ignore[assignment]

        setattr(obj, final_key, value)
        save_config(cfg)
        console.print(f"[green]✅ Set {key} = {value}[/green]")


@app.command()
def index(
    full: bool = typer.Option(False, "--full", help="Force full re-index"),
    status: bool = typer.Option(False, "--status", help="Show index state for current project"),
    clear: bool = typer.Option(False, "--clear", help="Wipe index for current project"),
) -> None:
    """Index the current project's codebase for semantic search."""
    import asyncio

    from specsync.core.project import detect_project_root
    from specsync.core.storage import (
        clear_project_index,
        ensure_dirs,
        get_changed_files_count,
        get_chroma_dir,
        get_index_status,
        get_sqlite_path,
    )

    # Detect project root
    project_root, found_marker = detect_project_root()
    if not found_marker:
        console.print(
            "[yellow]⚠️  No project marker found (.git, pyproject.toml, etc.). "
            f"Using current directory: {project_root}[/yellow]\n"
        )
    else:
        console.print(f"[dim]Project root: {project_root}[/dim]\n")

    ensure_dirs(project_root)
    sqlite_path = get_sqlite_path(project_root)

    # --- --status flag ---
    if status:
        idx_status = asyncio.run(get_index_status(sqlite_path))

        if not idx_status["exists"]:
            console.print(
                Panel(
                    "This project has not been indexed yet.\n"
                    "Run [bold cyan]specsync index[/bold cyan] to create the index.",
                    title="📊 Index Status",
                    border_style="yellow",
                )
            )
            return

        # Check for changes
        changes = asyncio.run(get_changed_files_count(project_root, sqlite_path))

        table = Table(title="📊 Index Status", border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Indexed files", str(idx_status["total_files"]))
        table.add_row("Total chunks", str(idx_status["total_chunks"]))
        table.add_row("Last indexed", idx_status["last_indexed"] or "never")
        table.add_row("Changed files", str(changes["changed"]))
        table.add_row("New files", str(changes["new"]))
        table.add_row("Deleted files", str(changes["deleted"]))

        console.print(table)

        total_changes = changes["changed"] + changes["new"] + changes["deleted"]
        if total_changes > 0:
            console.print(
                f"\n[yellow]⚠️  {total_changes} file(s) changed since last index. "
                "Run [bold]specsync index[/bold] to update.[/yellow]"
            )
        else:
            console.print("\n[green]✅ Index is up to date.[/green]")
        return

    # --- --clear flag ---
    if clear:
        chroma_dir = get_chroma_dir(project_root)
        if not sqlite_path.exists() and not chroma_dir.exists():
            console.print("[yellow]No index found for this project.[/yellow]")
            return

        if not Confirm.ask(
            "[red]This will delete the entire index for this project. Continue?[/red]",
            default=False,
        ):
            console.print("[dim]Cancelled.[/dim]")
            return

        clear_project_index(project_root)
        console.print("[green]✅ Index cleared successfully.[/green]")
        return

    # --- Default: run indexing ---
    if not config_exists():
        console.print(
            Panel(
                "No configuration found. Run [bold cyan]specsync init[/bold cyan] first.",
                title="❌ No Config",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    incremental = not full

    console.print(
        Panel(
            f"[bold cyan]Indexing project...[/bold cyan]\n"
            f"Mode: [cyan]{'incremental' if incremental else 'full rebuild'}[/cyan]\n"
            f"Project: [dim]{project_root}[/dim]",
            title="🔍 SpecSync Indexer",
            border_style="cyan",
        )
    )

    async def _run_index() -> dict:
        """Launch CodeSearchMCP and run indexing."""
        import json
        import sys

        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        from specsync.core.storage import get_config_path

        import os
        env = os.environ.copy()
        env["SPECSYNC_CONFIG_PATH"] = str(get_config_path())

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "specsync.mcp.servers.code_search.server"],
            env=env,
        )

        async with stdio_client(params) as transport:
            async with ClientSession(*transport) as session:
                await session.initialize()

                result = await session.call_tool(
                    "index_codebase",
                    {
                        "project_root": str(project_root.resolve()),
                        "incremental": incremental,
                    },
                )

                if result.isError:
                    error_text = result.content[0].text if result.content else "Unknown error"
                    raise RuntimeError(f"Indexing failed: {error_text}")

                text = result.content[0].text if result.content else "{}"
                return json.loads(text)

    try:
        with console.status("[cyan]Indexing codebase (this may take a moment on first run)...[/cyan]"):
            result = asyncio.run(_run_index())

        # Show summary
        table = Table(border_style="green")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Files indexed", str(result.get("files_indexed", 0)))
        table.add_row("Chunks created", str(result.get("chunks_created", 0)))
        table.add_row("Files skipped (unchanged)", str(result.get("files_skipped", 0)))
        table.add_row("Duration", f"{result.get('duration_seconds', 0):.1f}s")

        console.print()
        console.print(table)

        chroma_dir = get_chroma_dir(project_root)
        console.print(f"\n[dim]Index stored at: {chroma_dir.parent}[/dim]")
        console.print("[green]✅ Indexing complete.[/green]")

    except Exception as exc:
        console.print(
            Panel(
                f"[red bold]Indexing failed[/red bold]\n\n{exc}",
                title="❌ Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command()
def analyze(
    issue: Optional[int] = typer.Option(None, "--issue", "-i", help="GitHub issue number to analyze"),
    spec: Optional[str] = typer.Option(None, "--spec", "-s", help="Path to a spec file (markdown/text)"),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Inline spec text to analyze"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="Output format: terminal, markdown, both, json",
    ),
    repo: Optional[str] = typer.Option(
        None, "--repo", "-r", help="GitHub repo (owner/repo) — overrides default"
    ),
) -> None:
    """Run full gap analysis on a spec against the current codebase."""
    import asyncio

    from specsync.agents.pipeline import run_pipeline
    from specsync.core.project import detect_project_root
    from specsync.core.storage import ensure_dirs
    from specsync.mcp.manager import MCPManager

    # Validate inputs
    if not any([issue, spec, text]):
        console.print("[red]Error: Provide one of --issue, --spec, or --text[/red]")
        raise typer.Exit(1)

    # Load config
    if not config_exists():
        console.print(
            Panel(
                "No configuration found. Run [bold cyan]specsync init[/bold cyan] first.",
                title="❌ No Config",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    cfg = load_config()

    # Detect project root
    project_root, found_marker = detect_project_root()
    if not found_marker:
        console.print(
            "[yellow]⚠️  No project marker found (.git, pyproject.toml, etc.). "
            f"Using current directory: {project_root}[/yellow]\n"
        )
    else:
        console.print(f"[dim]Project root: {project_root}[/dim]\n")

    ensure_dirs(project_root)

    # Get spec text
    spec_text = ""
    spec_source = ""
    if text:
        spec_text = text
        spec_source = "inline"
    elif spec:
        spec_path = Path(spec)
        if not spec_path.exists():
            console.print(f"[red]Spec file not found: {spec}[/red]")
            raise typer.Exit(1)
        spec_text = spec_path.read_text(encoding="utf-8")
        spec_source = str(spec_path)
    elif issue:
        # Fetch from GitHub
        if not cfg.github.token:
            console.print("[red]GitHub token required for --issue[/red]")
            raise typer.Exit(1)
        if repo:
            owner, repo_name = repo.split("/", 1)
        elif cfg.github.default_repo:
            owner, repo_name = cfg.github.default_repo.split("/", 1)
        else:
            console.print("[red]Provide --repo or set github.default_repo in config[/red]")
            raise typer.Exit(1)

        console.print(f"[cyan]Fetching issue {issue} from {owner}/{repo_name}...[/cyan]")
        # TODO: Implement GitHub issue fetching via MCP
        console.print("[yellow]GitHub issue fetching not yet implemented. Use --spec or --text.[/yellow]")
        raise typer.Exit(1)

    # Run pipeline
    async def _run():
        async with MCPManager(cfg, project_root) as manager:
            report = await run_pipeline(cfg, manager, spec_text, spec_source, str(project_root))
            return report

    try:
        report = asyncio.run(_run())
        console.print(f"\n[green]✅ Analysis complete![/green]")
        console.print(f"\n[dim]Report generated at: {report.generated_at}[/dim]")
        console.print(f"\n[dim]{len(report.reuse)} reusable, {len(report.extend)} to extend, "
                     f"{len(report.conflicts)} conflicts, {len(report.net_new)} net new[/dim]")
    except Exception as exc:
        console.print(
            Panel(
                f"[red bold]Analysis failed[/red bold]\n\n{exc}",
                title="❌ Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Semantic search query"),
) -> None:
    """Semantic search across the indexed codebase."""
    console.print("[yellow]Not yet implemented.[/yellow]")


@app.command()
def reports(
    show: Optional[str] = typer.Option(
        None, "--show", help="Re-display a saved report by ID"
    ),
) -> None:
    """List or display saved analysis reports for the current project."""
    console.print("[yellow]Not yet implemented.[/yellow]")


@app.command()
def doctor() -> None:
    """Check that all dependencies and services are working."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]SpecSync Doctor[/bold cyan]\n"
            "Checking all dependencies and services...",
            border_style="cyan",
        )
    )
    console.print()

    table = Table(border_style="dim")
    table.add_column("Service", style="bold", min_width=20)
    table.add_column("Status", justify="center", min_width=8)
    table.add_column("Details")

    # 1. Config file
    if config_exists():
        try:
            cfg = load_config()
            table.add_row("Config File", "✅", str(get_config_path()))
        except Exception as exc:
            cfg = None
            table.add_row("Config File", "❌", f"Invalid: {exc}")
    else:
        cfg = None
        table.add_row("Config File", "❌", "Not found — run: specsync init")

    # 2. LLM provider
    if cfg:
        with console.status("[dim]Checking LLM provider...[/dim]"):
            if cfg.llm.provider == "ollama":
                ok, msg = _validate_ollama(cfg.llm.base_url, cfg.llm.model)
            else:
                ok = bool(cfg.llm.api_key)
                msg = f"API key configured for {cfg.llm.provider}" if ok else "No API key"
        table.add_row(
            f"LLM ({cfg.llm.provider})",
            "✅" if ok else "❌",
            msg,
        )
    else:
        table.add_row("LLM Provider", "❌", "No config")

    # 3. GitHub token
    if cfg and cfg.github.token:
        with console.status("[dim]Checking GitHub token...[/dim]"):
            ok, msg = _validate_github_token(cfg.github.token)
        table.add_row("GitHub Token", "✅" if ok else "❌", msg)
    else:
        table.add_row("GitHub Token", "❌", "Not configured")

    # 4. Search provider
    if cfg:
        if cfg.search_provider == "brave" and cfg.brave.api_key:
            with console.status("[dim]Checking Brave Search...[/dim]"):
                ok, msg = _validate_brave_key(cfg.brave.api_key)
            table.add_row("Brave Search", "✅" if ok else "❌", msg)
        elif cfg.search_provider == "searchx" and cfg.searchx.api_key:
            with console.status("[dim]Checking SearchX...[/dim]"):
                ok, msg = _validate_searchx_key(cfg.searchx.api_key)
            table.add_row("SearchX", "✅" if ok else "❌", msg)
        else:
            table.add_row(f"{cfg.search_provider.capitalize()} Search", "⚠️", "Not configured (optional)")
    else:
        table.add_row("Search Provider", "❌", "No config")

    # 5. Node.js
    ok, msg = _check_command(["node", "--version"])
    table.add_row("Node.js", "✅" if ok else "❌", msg if ok else "Not found — download from nodejs.org")

    # 6. npx
    ok, msg = _check_command(["npx", "--version"])
    table.add_row("npx", "✅" if ok else "❌", msg if ok else "Not found — install Node.js")

    console.print(table)
    console.print()


if __name__ == "__main__":
    app()
