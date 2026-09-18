"""Phase 11 — Web tools: web_search and fetch_url tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry():
    from devagent.tools.registry import ToolRegistry
    return ToolRegistry()


def _brave_response(results: list[dict]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"web": {"results": results}}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _searchx_response(results: list[dict]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": results}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _html_response(html: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _text_response(text: str, content_type: str = "text/plain") -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_resp.headers = {"content-type": content_type}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# 11.1 fetch_url — always registered
# ---------------------------------------------------------------------------

class TestFetchUrl:
    def test_fetch_url_always_registered(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        # No API keys — fetch_url should still be registered
        register_web_tools(reg)
        assert "fetch_url" in reg.names()

    def test_fetch_url_html_extracts_text(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        html = "<html><head><title>T</title></head><body><p>Hello world</p></body></html>"
        with patch("httpx.get", return_value=_html_response(html)):
            result = reg.call("fetch_url", {"url": "http://example.com", "extract_text": True})
        assert "Hello world" in result
        assert "<p>" not in result

    def test_fetch_url_strips_script_tags(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        html = "<html><body><script>var x=1;</script><p>Visible</p></body></html>"
        with patch("httpx.get", return_value=_html_response(html)):
            result = reg.call("fetch_url", {"url": "http://example.com"})
        assert "var x" not in result
        assert "Visible" in result

    def test_fetch_url_returns_plain_text_unchanged(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        with patch("httpx.get", return_value=_text_response("raw text content")):
            result = reg.call("fetch_url", {"url": "http://example.com/data.txt"})
        assert "raw text content" in result

    def test_fetch_url_requires_url(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        result = reg.call("fetch_url", {})
        assert "[error]" in result

    def test_fetch_url_handles_http_error(self) -> None:
        import httpx

        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = reg.call("fetch_url", {"url": "http://unreachable.invalid"})
        assert "[error]" in result


# ---------------------------------------------------------------------------
# 11.2 web_search — Brave provider
# ---------------------------------------------------------------------------

class TestWebSearchBrave:
    def _make_reg(self) -> object:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(
            reg,
            brave_api_key="test-brave-key",
            search_provider="brave",
        )
        return reg

    def test_web_search_registered_when_brave_key_set(self) -> None:
        reg = self._make_reg()
        assert "web_search" in reg.names()

    def test_brave_search_returns_results(self) -> None:
        reg = self._make_reg()
        results = [
            {"title": "Python docs", "url": "https://docs.python.org", "description": "Official Python docs"},
            {"title": "PyPI", "url": "https://pypi.org", "description": "Python package index"},
        ]
        with patch("httpx.get", return_value=_brave_response(results)):
            result = reg.call("web_search", {"query": "python packaging"})
        assert "Python docs" in result
        assert "docs.python.org" in result
        assert "PyPI" in result

    def test_brave_search_sends_correct_headers(self) -> None:
        reg = self._make_reg()
        with patch("httpx.get", return_value=_brave_response([])) as mock_get:
            reg.call("web_search", {"query": "test"})
        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert "X-Subscription-Token" in headers
        assert headers["X-Subscription-Token"] == "test-brave-key"

    def test_brave_search_no_results(self) -> None:
        reg = self._make_reg()
        with patch("httpx.get", return_value=_brave_response([])):
            result = reg.call("web_search", {"query": "xyzzy totally unreal query"})
        assert "No results" in result

    def test_brave_search_num_results_respected(self) -> None:
        reg = self._make_reg()
        results = [{"title": f"R{i}", "url": f"http://r{i}.com", "description": ""} for i in range(10)]
        with patch("httpx.get", return_value=_brave_response(results)):
            result = reg.call("web_search", {"query": "test", "num_results": 3})
        # Only 3 results should be in output (R0, R1, R2 not R3+)
        assert "R2" in result
        assert "R3" not in result

    def test_web_search_requires_query(self) -> None:
        reg = self._make_reg()
        result = reg.call("web_search", {})
        assert "[error]" in result


# ---------------------------------------------------------------------------
# 11.3 web_search — SearchX provider
# ---------------------------------------------------------------------------

class TestWebSearchSearchX:
    def _make_reg(self, base_url: str = "http://localhost:8888") -> object:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(
            reg,
            searchx_base_url=base_url,
            search_provider="searchx",
        )
        return reg

    def test_web_search_registered_for_searchx(self) -> None:
        reg = self._make_reg()
        assert "web_search" in reg.names()

    def test_searchx_search_returns_results(self) -> None:
        reg = self._make_reg()
        results = [
            {"title": "SearXNG docs", "url": "https://searxng.org", "content": "Meta search engine"},
        ]
        with patch("httpx.get", return_value=_searchx_response(results)):
            result = reg.call("web_search", {"query": "searxng"})
        assert "SearXNG docs" in result
        assert "searxng.org" in result

    def test_searchx_hits_correct_endpoint(self) -> None:
        reg = self._make_reg(base_url="http://mysearch:9090")
        with patch("httpx.get", return_value=_searchx_response([])) as mock_get:
            reg.call("web_search", {"query": "test"})
        url_called = mock_get.call_args.args[0]
        assert "mysearch:9090" in url_called
        assert "/search" in url_called


# ---------------------------------------------------------------------------
# 11.4 HTML text extractor (unit test the helper directly)
# ---------------------------------------------------------------------------

class TestHtmlToText:
    def test_strips_html_tags(self) -> None:
        from devagent.tools.web_tools import _html_to_text
        result = _html_to_text("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_skips_script_content(self) -> None:
        from devagent.tools.web_tools import _html_to_text
        result = _html_to_text("<p>Visible</p><script>alert('xss')</script>")
        assert "Visible" in result
        assert "alert" not in result

    def test_skips_style_content(self) -> None:
        from devagent.tools.web_tools import _html_to_text
        result = _html_to_text("<style>body{color:red}</style><p>Text</p>")
        assert "color" not in result
        assert "Text" in result

    def test_collapses_whitespace(self) -> None:
        from devagent.tools.web_tools import _html_to_text
        result = _html_to_text("<p>  lots   of   spaces  </p>")
        assert "  " not in result.strip()


# ---------------------------------------------------------------------------
# 11.5 SearchXConfig base_url field
# ---------------------------------------------------------------------------

class TestSearchXConfig:
    def test_searchx_config_has_base_url(self) -> None:
        from devagent.core.config import SearchXConfig
        cfg = SearchXConfig()
        assert cfg.base_url == "http://localhost:8888"

    def test_searchx_config_base_url_configurable(self) -> None:
        from devagent.core.config import SearchXConfig
        cfg = SearchXConfig(base_url="http://search.internal:9090")
        assert "9090" in cfg.base_url

    def test_devagent_config_exposes_searchx_base_url(self) -> None:
        from devagent.core.config import DevAgentConfig
        cfg = DevAgentConfig()
        assert hasattr(cfg.searchx, "base_url")
