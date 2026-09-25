"""Tests for Phase 27 — Ollama Cloud support."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from devagent.core.config import LLMConfig

# ---------------------------------------------------------------------------
# _ollama_client() — correct client construction
# ---------------------------------------------------------------------------

class TestOllamaClient:
    def _client(self, base_url="http://localhost:11434", api_key="", model="llama3.2"):
        from devagent.core.llm import LLMClient
        cfg = LLMConfig(provider="ollama", model=model, base_url=base_url, api_key=api_key)
        return LLMClient(cfg)

    def test_local_default_returns_plain_client(self):
        """No custom config → plain Client() with no extra args."""
        lc = self._client()
        with patch("ollama.Client") as MockClient:
            MockClient.return_value = MagicMock()
            lc._ollama_client()
        MockClient.assert_called_once_with()

    def test_cloud_api_key_uses_ollama_com(self):
        """api_key set with default base_url → host=https://ollama.com + Bearer header."""
        lc = self._client(api_key="sk-test-key")
        with patch("ollama.Client") as MockClient:
            MockClient.return_value = MagicMock()
            lc._ollama_client()
        MockClient.assert_called_once_with(
            host="https://ollama.com",
            headers={"Authorization": "Bearer sk-test-key"},
        )

    def test_cloud_api_key_with_custom_base_url(self):
        """api_key + explicit base_url → uses that URL, not ollama.com."""
        lc = self._client(base_url="https://custom.ollama.host", api_key="mykey")
        with patch("ollama.Client") as MockClient:
            MockClient.return_value = MagicMock()
            lc._ollama_client()
        MockClient.assert_called_once_with(
            host="https://custom.ollama.host",
            headers={"Authorization": "Bearer mykey"},
        )

    def test_non_default_base_url_no_key(self):
        """Custom base_url but no key → Client(host=url) only."""
        lc = self._client(base_url="http://192.168.1.5:11434")
        with patch("ollama.Client") as MockClient:
            MockClient.return_value = MagicMock()
            lc._ollama_client()
        MockClient.assert_called_once_with(host="http://192.168.1.5:11434")

    def test_bearer_token_format(self):
        """Header value must be exactly 'Bearer <key>'."""
        lc = self._client(api_key="abc123")
        with patch("ollama.Client") as MockClient:
            MockClient.return_value = MagicMock()
            lc._ollama_client()
        _, kwargs = MockClient.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer abc123"

    def test_empty_api_key_treated_as_local(self):
        """Empty api_key string (falsy) → local client, no headers."""
        lc = self._client(api_key="")
        with patch("ollama.Client") as MockClient:
            MockClient.return_value = MagicMock()
            lc._ollama_client()
        MockClient.assert_called_once_with()


# ---------------------------------------------------------------------------
# _ollama() uses _ollama_client(), not bare ollama.chat()
# ---------------------------------------------------------------------------

class TestOllamaDispatch:
    def _make_resp(self, content="hello", tool_calls=None):
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls or []
        resp = MagicMock()
        resp.message = msg
        resp.prompt_eval_count = 10
        resp.eval_count = 5
        return resp

    def test_cloud_call_uses_client_chat(self):
        """_ollama() must call client.chat(), not module-level ollama.chat()."""
        from devagent.core.llm import LLMClient
        cfg = LLMConfig(provider="ollama", model="gpt-oss:20b",
                        base_url="https://ollama.com", api_key="sk-cloud")
        lc = LLMClient(cfg)

        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_resp("cloud response")

        from devagent.core.llm import AgentMessage
        msgs = [AgentMessage(role="user", content="hello")]

        with patch.object(lc, "_ollama_client", return_value=mock_client):
            result = lc._ollama(msgs, tools=None)

        mock_client.chat.assert_called_once()
        assert result.content == "cloud response"
        assert result.provider == "ollama"

    def test_local_call_uses_client_chat(self):
        """_ollama() uses client.chat() for local too (via plain Client())."""
        from devagent.core.llm import AgentMessage, LLMClient
        cfg = LLMConfig(provider="ollama", model="llama3.2")
        lc = LLMClient(cfg)

        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_resp("local response")
        msgs = [AgentMessage(role="user", content="hi")]

        with patch.object(lc, "_ollama_client", return_value=mock_client):
            result = lc._ollama(msgs, tools=None)

        mock_client.chat.assert_called_once()
        assert result.content == "local response"


# ---------------------------------------------------------------------------
# _validate_ollama — cloud URL skips local check
# ---------------------------------------------------------------------------

class TestValidateOllama:
    def test_cloud_url_skips_local_check(self):
        from devagent.cli import _validate_ollama
        ok, msg = _validate_ollama("https://ollama.com", "gpt-oss:20b")
        assert ok is True
        assert "Cloud" in msg

    def test_local_url_tries_to_connect(self):
        """Local URL attempts an HTTP check (will fail in test — that's expected)."""
        from devagent.cli import _validate_ollama
        with patch("devagent.cli.httpx.get", side_effect=Exception("no server")):
            ok, _msg = _validate_ollama("http://localhost:11434", "llama3.2")
        assert ok is False


# ---------------------------------------------------------------------------
# Config round-trip — api_key and base_url survive save/load
# ---------------------------------------------------------------------------

class TestOllamaCloudConfig:
    def test_cloud_config_fields_preserved(self):
        from devagent.core.config import DevAgentConfig, LLMConfig
        cfg = DevAgentConfig(
            llm=LLMConfig(
                provider="ollama",
                model="gpt-oss:20b",
                base_url="https://ollama.com",
                api_key="sk-test",
            )
        )
        assert cfg.llm.base_url == "https://ollama.com"
        assert cfg.llm.api_key == "sk-test"
        assert cfg.llm.provider == "ollama"

    def test_save_and_reload_preserves_cloud_config(self, tmp_path):
        import tomllib

        import tomli_w

        from devagent.core.config import DevAgentConfig, LLMConfig

        cfg = DevAgentConfig(
            llm=LLMConfig(
                provider="ollama",
                model="gpt-oss:120b",
                base_url="https://ollama.com",
                api_key="sk-mykey",
            )
        )
        config_file = tmp_path / "settings.toml"
        data = cfg.model_dump(exclude_none=True)
        with open(config_file, "wb") as f:
            tomli_w.dump(data, f)

        with open(config_file, "rb") as f:
            loaded = tomllib.load(f)

        assert loaded["llm"]["base_url"] == "https://ollama.com"
        assert loaded["llm"]["api_key"] == "sk-mykey"
        assert loaded["llm"]["model"] == "gpt-oss:120b"
