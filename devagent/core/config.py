"""Configuration loading and saving using platformdirs + tomllib.

The config file is a TOML file stored at get_config_path().
All config models are Pydantic models with sensible defaults.
"""

from __future__ import annotations

import tomllib
from typing import Literal

import tomli_w
from pydantic import BaseModel

from devagent.core.storage import get_config_path


class LLMFallbackConfig(BaseModel):
    """Optional fallback LLM provider configuration."""
    provider: str = ""
    model: str = ""
    api_key: str = ""


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "ollama"
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    api_key: str = ""
    fallback: LLMFallbackConfig | None = None


class GitHubConfig(BaseModel):
    """GitHub integration configuration."""
    token: str = ""
    default_repo: str = ""


class BraveConfig(BaseModel):
    """Brave Search API configuration."""
    api_key: str = ""


class SearchXConfig(BaseModel):
    """SearchX API configuration."""
    api_key: str = ""


class OutputConfig(BaseModel):
    """Output formatting preferences."""
    verbosity: Literal["quiet", "normal", "verbose"] = "normal"


class WatcherConfig(BaseModel):
    """Repo Health Monitor configuration."""
    default_interval_minutes: int = 30
    max_issues_per_check: int = 20
    default_labels: list[str] = []
    notify_on_cross_conflict: bool = True
    skip_closed_issues: bool = True


# ---------------------------------------------------------------------------
# Phase 1+ — Agent harness config sections
# ---------------------------------------------------------------------------

class RouterConfig(BaseModel):
    """Multi-model routing: maps task type → (provider, model) pair."""
    planning: dict[str, str] = {"provider": "ollama", "model": "qwen2.5-coder:14b"}
    coding: dict[str, str] = {"provider": "ollama", "model": "qwen2.5-coder:7b"}
    reviewing: dict[str, str] = {"provider": "ollama", "model": "qwen2.5-coder:7b"}
    cheap: dict[str, str] = {"provider": "ollama", "model": "qwen2.5-coder:3b"}
    fallback: dict[str, str] = {"provider": "ollama", "model": "qwen2.5-coder:7b"}


class AgentConfig(BaseModel):
    """Core agent loop configuration."""
    max_iterations: int = 50
    max_repair_iterations: int = 3
    stream_thoughts: bool = True
    confirmation_required: bool = True
    auto_run_tests: bool = True
    loop_detection: bool = True       # detect repeated identical tool calls and bail early
    shell_output_cap_kb: int = 0      # 0 = unlimited; stream large output to temp file
    shell_timeout_sec: int = 300      # per-command timeout in seconds (0 = no timeout)


class SessionConfig(BaseModel):
    """Session persistence configuration."""
    auto_resume: bool = True
    max_sessions: int = 20


class SecurityConfig(BaseModel):
    """Security Gate configuration."""
    gate_enabled: bool = True
    block_on_secrets: bool = True
    warn_on_weak_crypto: bool = True
    check_new_dependencies: bool = True


class TokenBudgetConfig(BaseModel):
    """Token budget and cost tracking."""
    session_cap_usd: float = 0.0
    warn_at_percent: int = 80
    track_by_model: bool = True


class CodePrismConfig(BaseModel):
    """CodePrism knowledge graph integration."""
    auto_index: bool = True
    mcp_transport: Literal["stdio", "sse"] = "stdio"
    mcp_port: int = 8765


class DevAgentConfig(BaseModel):
    """Root configuration model for DevAgent."""
    llm: LLMConfig = LLMConfig()
    github: GitHubConfig = GitHubConfig()
    brave: BraveConfig = BraveConfig()
    searchx: SearchXConfig = SearchXConfig()
    search_provider: Literal["brave", "searchx"] = "searchx"
    output: OutputConfig = OutputConfig()
    watcher: WatcherConfig = WatcherConfig()
    # Phase 1+ agent harness config
    router: RouterConfig = RouterConfig()
    agent: AgentConfig = AgentConfig()
    session: SessionConfig = SessionConfig()
    security: SecurityConfig = SecurityConfig()
    budget: TokenBudgetConfig = TokenBudgetConfig()
    codeprism: CodePrismConfig = CodePrismConfig()


def config_exists() -> bool:
    """Check if the config file exists."""
    return get_config_path().is_file()


def load_config() -> DevAgentConfig:
    """Read the TOML config file and return a DevAgentConfig model.

    Returns defaults if the file does not exist.
    """
    config_path = get_config_path()
    if not config_path.is_file():
        return DevAgentConfig()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return DevAgentConfig(**data)


def save_config(config: DevAgentConfig) -> None:
    """Write the DevAgentConfig model to the TOML config file.

    Creates parent directories if they don't exist.
    """
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert Pydantic model to dict, excluding None values for cleaner TOML
    data = config.model_dump(exclude_none=True)

    # Remove empty fallback section to keep config clean
    if "llm" in data and "fallback" in data["llm"]:
        fallback = data["llm"]["fallback"]
        if not fallback.get("provider"):
            del data["llm"]["fallback"]

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)
