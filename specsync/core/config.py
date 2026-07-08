"""Configuration loading and saving using platformdirs + tomllib.

The config file is a TOML file stored at get_config_path().
All config models are Pydantic models with sensible defaults.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal, Optional

import tomli_w
from pydantic import BaseModel

from specsync.core.storage import get_config_path


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
    fallback: Optional[LLMFallbackConfig] = None


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


class SpecSyncConfig(BaseModel):
    """Root configuration model for SpecSync."""
    llm: LLMConfig = LLMConfig()
    github: GitHubConfig = GitHubConfig()
    brave: BraveConfig = BraveConfig()
    searchx: SearchXConfig = SearchXConfig()
    search_provider: Literal["brave", "searchx"] = "searchx"
    output: OutputConfig = OutputConfig()


def config_exists() -> bool:
    """Check if the config file exists."""
    return get_config_path().is_file()


def load_config() -> SpecSyncConfig:
    """Read the TOML config file and return a SpecSyncConfig model.

    Returns defaults if the file does not exist.
    """
    config_path = get_config_path()
    if not config_path.is_file():
        return SpecSyncConfig()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return SpecSyncConfig(**data)


def save_config(config: SpecSyncConfig) -> None:
    """Write the SpecSyncConfig model to the TOML config file.

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
