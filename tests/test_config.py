from pathlib import Path

from devagent.core.config import (
    DevAgentConfig,
    config_exists,
    load_config,
    save_config,
)


def test_config_defaults():
    config = DevAgentConfig()
    assert config.llm.provider == "ollama"
    assert config.llm.model == "qwen2.5-coder:7b"
    assert config.llm.base_url == "http://localhost:11434"
    assert config.output.verbosity == "normal"
    assert config.search_provider == "searchx"

def test_config_reads_writes_correctly(mock_config_path: Path, monkeypatch):
    # Ensure the mocked path is used
    monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(mock_config_path))
    
    config = DevAgentConfig()
    config.github.token = "test_token_123"
    config.llm.provider = "openai"
    config.llm.model = "gpt-4o"

    assert not config_exists()

    save_config(config)

    assert config_exists()
    assert mock_config_path.exists()

    loaded = load_config()
    assert loaded.github.token == "test_token_123"
    assert loaded.llm.provider == "openai"
    assert loaded.llm.model == "gpt-4o"
    assert loaded.output.verbosity == "normal"

def test_config_path_resolution(monkeypatch, tmp_path):
    # Clear any existing env var first
    monkeypatch.delenv("SPECSYNC_CONFIG_PATH", raising=False)
    
    # If SPECSYNC_CONFIG_PATH is set
    env_path = tmp_path / "custom_config.toml"
    monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(env_path))
    from devagent.core.storage import get_config_path

    assert get_config_path() == env_path

    # If not set, it uses platformdirs
    monkeypatch.delenv("SPECSYNC_CONFIG_PATH", raising=False)
    default_path = get_config_path()
    assert default_path.name == "config.toml"
    assert "devagent" in str(default_path).lower()
