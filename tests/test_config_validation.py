"""A config file that is present but invalid must fail loudly, not become defaults.

Regression tests for the silent-fallback path in ``devagent.core.config.load_config``:
previously the whole construction was wrapped in ``except Exception: return
DevAgentConfig()``, so any validation error was discarded and the agent ran with
values the user never chose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devagent.core.config import ConfigError, DevAgentConfig, load_config


def _use_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Path:
    """Point the user-config path at a temp file containing ``text``."""
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(path))
    return path


def _use_project_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Path:
    """Write a committed project settings file under ``tmp_path``."""
    monkeypatch.delenv("SPECSYNC_CONFIG_PATH", raising=False)
    monkeypatch.delenv("DEVAGENT_CONFIG_PATH", raising=False)
    monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(tmp_path / "absent-user-config.toml"))
    path = tmp_path / ".devagent" / "settings.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Absent config is not an error — defaults are still the fallback
# ---------------------------------------------------------------------------

class TestAbsentConfigStillUsesDefaults:
    def test_no_files_returns_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(tmp_path / "nope.toml"))
        cfg = load_config(tmp_path)
        assert cfg == DevAgentConfig()

    def test_empty_project_dir_returns_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SPECSYNC_CONFIG_PATH", raising=False)
        monkeypatch.delenv("DEVAGENT_CONFIG_PATH", raising=False)
        monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(tmp_path / "nope.toml"))
        assert load_config(tmp_path).llm.provider == "ollama"


# ---------------------------------------------------------------------------
# Present-but-invalid config raises ConfigError and names the file
# ---------------------------------------------------------------------------

class TestInvalidConfigRaises:
    def test_invalid_enum_value_user_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = _use_user_config(tmp_path, monkeypatch, '[llm]\neffort = "extreme"\n')
        with pytest.raises(ConfigError) as excinfo:
            load_config()
        assert str(path) in str(excinfo.value)
        assert "effort" in str(excinfo.value)

    def test_invalid_enum_value_project_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = _use_project_config(tmp_path, monkeypatch, '[output]\nverbosity = "loud"\n')
        with pytest.raises(ConfigError) as excinfo:
            load_config(tmp_path)
        assert str(path) in str(excinfo.value)
        assert "verbosity" in str(excinfo.value)

    def test_wrong_type_is_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_user_config(tmp_path, monkeypatch, '[agent]\nmax_iterations = "many"\n')
        with pytest.raises(ConfigError):
            load_config()

    def test_top_level_literal_is_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_user_config(tmp_path, monkeypatch, 'search_provider = "duckduckgo"\n')
        with pytest.raises(ConfigError):
            load_config()

    def test_malformed_toml_is_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = _use_user_config(tmp_path, monkeypatch, "[llm\nprovider = ")
        with pytest.raises(ConfigError) as excinfo:
            load_config()
        assert str(path) in str(excinfo.value)

    def test_error_chain_preserves_cause(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_user_config(tmp_path, monkeypatch, '[llm]\neffort = "extreme"\n')
        with pytest.raises(ConfigError) as excinfo:
            load_config()
        assert excinfo.value.__cause__ is not None


# ---------------------------------------------------------------------------
# Valid config is still honoured (control arm — the fix must not reject good files)
# ---------------------------------------------------------------------------

class TestValidConfigStillLoads:
    def test_values_are_applied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_user_config(tmp_path, monkeypatch, '[llm]\neffort = "low"\n[output]\nverbosity = "quiet"\n')
        cfg = load_config()
        assert cfg.llm.effort == "low"
        assert cfg.output.verbosity == "quiet"

    def test_project_config_overrides_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_user_config(tmp_path, monkeypatch, '[output]\nverbosity = "quiet"\n')
        project = tmp_path / ".devagent" / "settings.toml"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_text('[output]\nverbosity = "verbose"\n', encoding="utf-8")
        assert load_config(tmp_path).output.verbosity == "verbose"


# ---------------------------------------------------------------------------
# Diagnostic note: which fields can actually reject a value
# ---------------------------------------------------------------------------

class TestWhichFieldsValidate:
    """``LLMConfig.provider`` is a free-form ``str``, so the issue's own repro
    (``provider = "nonexistent_provider"``) is accepted and reaches the runtime —
    only Literal-typed and typed fields raise. Pinned so the boundary is explicit.
    """

    def test_provider_is_free_form(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_user_config(tmp_path, monkeypatch, '[llm]\nprovider = "nonexistent_provider"\n')
        assert load_config().llm.provider == "nonexistent_provider"

    def test_effort_is_constrained(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_user_config(tmp_path, monkeypatch, '[llm]\neffort = "extreme"\n')
        with pytest.raises(ConfigError):
            load_config()
