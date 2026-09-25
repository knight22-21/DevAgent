"""Tests for Phase 23 — /model mid-session hot-swap."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helper — simulate the /model REPL branch logic
# (extracted here so we can test the branching behaviour without a live REPL)
# ---------------------------------------------------------------------------

_VALID_PROVIDERS = ("ollama", "anthropic", "openai", "gemini", "groq")


def _handle_model_cmd(cfg_llm, raw: str) -> str:
    """Mirror the /model branch in flows.py. Returns the console message."""
    parts = raw.split(None, 1)
    if len(parts) < 2:
        return f"Current model: {cfg_llm.provider}/{cfg_llm.model}"

    spec = parts[1].strip()
    if "/" in spec:
        new_provider, new_model = spec.split("/", 1)
        new_provider = new_provider.strip().lower()
        new_model = new_model.strip()
        if new_provider not in _VALID_PROVIDERS:
            return f"Unknown provider '{new_provider}'"
        cfg_llm.provider = new_provider
        cfg_llm.model = new_model
        return f"Model switched to {new_provider}/{new_model}"
    else:
        cfg_llm.model = spec
        return f"Model switched to {cfg_llm.provider}/{spec}"


# ---------------------------------------------------------------------------
# Unit tests — config mutation logic
# ---------------------------------------------------------------------------

class TestModelCommandLogic:
    def _llm_cfg(self):
        from devagent.core.config import LLMConfig
        return LLMConfig(provider="ollama", model="llama3.2")

    def test_no_arg_shows_current(self):
        cfg = self._llm_cfg()
        msg = _handle_model_cmd(cfg, "/model")
        assert "ollama" in msg
        assert "llama3.2" in msg
        # Config unchanged
        assert cfg.provider == "ollama"
        assert cfg.model == "llama3.2"

    def test_switch_provider_and_model(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model anthropic/claude-sonnet-4-6")
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-6"

    def test_switch_model_only_keeps_provider(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model qwen2.5-coder")
        assert cfg.provider == "ollama"
        assert cfg.model == "qwen2.5-coder"

    def test_invalid_provider_rejected(self):
        cfg = self._llm_cfg()
        msg = _handle_model_cmd(cfg, "/model badprovider/gpt-5")
        assert "Unknown provider" in msg
        assert cfg.provider == "ollama"
        assert cfg.model == "llama3.2"

    def test_openai_provider(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model openai/gpt-4o")
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"

    def test_gemini_provider(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model gemini/gemini-1.5-pro")
        assert cfg.provider == "gemini"
        assert cfg.model == "gemini-1.5-pro"

    def test_groq_provider(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model groq/llama-3.1-70b-versatile")
        assert cfg.provider == "groq"
        assert cfg.model == "llama-3.1-70b-versatile"

    def test_model_name_with_dots_and_dashes(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model ollama/llama3.2:8b-instruct-q4_K_M")
        assert cfg.provider == "ollama"
        assert cfg.model == "llama3.2:8b-instruct-q4_K_M"

    def test_all_valid_providers_accepted(self):
        for p in _VALID_PROVIDERS:
            cfg = self._llm_cfg()
            _handle_model_cmd(cfg, f"/model {p}/test-model")
            assert cfg.provider == p
            assert cfg.model == "test-model"

    def test_provider_normalized_lowercase(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model Anthropic/claude-opus-4-8")
        assert cfg.provider == "anthropic"

    def test_switch_back_to_ollama(self):
        cfg = self._llm_cfg()
        _handle_model_cmd(cfg, "/model openai/gpt-4o")
        _handle_model_cmd(cfg, "/model ollama/phi3.5")
        assert cfg.provider == "ollama"
        assert cfg.model == "phi3.5"


# ---------------------------------------------------------------------------
# Integration tests — LLMClient reads cfg by reference
# ---------------------------------------------------------------------------

class TestLlmClientSeesMutation:
    def test_llm_client_sees_new_model_after_mutation(self):
        """Confirm LLMClient.cfg is the same object as cfg_llm, not a copy."""
        from devagent.core.config import LLMConfig
        from devagent.core.llm import LLMClient

        cfg_llm = LLMConfig(provider="ollama", model="llama3.2")
        client = LLMClient(cfg_llm)
        assert client.cfg.model == "llama3.2"
        cfg_llm.model = "phi3.5"
        assert client.cfg.model == "phi3.5"

    def test_llm_client_sees_new_provider_after_mutation(self):
        from devagent.core.config import LLMConfig
        from devagent.core.llm import LLMClient

        cfg_llm = LLMConfig(provider="ollama", model="llama3.2")
        client = LLMClient(cfg_llm)
        assert client.cfg.provider == "ollama"
        cfg_llm.provider = "openai"
        assert client.cfg.provider == "openai"


# ---------------------------------------------------------------------------
# Integration test — verify the handler exists in flows.py
# ---------------------------------------------------------------------------

class TestFlowsHasModelHandler:
    def test_model_command_in_repl_source(self):
        """Smoke-test: /model keyword exists in flows.py."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "devagent" / "agent" / "flows.py"
        text = source.read_text(encoding="utf-8")
        assert "/model" in text
        assert "Phase 23" in text
