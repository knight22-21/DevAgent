"""Phase 11 — Web tools: web_search and fetch_url tests."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

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


def _addrinfo(address: str, port: int) -> list[tuple]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


def _record_request_response(
    requests: list[httpx.Request], request: httpx.Request, response: httpx.Response
) -> httpx.Response:
    requests.append(request)
    return response


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
        with patch(
            "devagent.tools.web_tools._fetch_url_response", return_value=_html_response(html)
        ):
            result = reg.call("fetch_url", {"url": "http://example.com", "extract_text": True})
        assert "Hello world" in result
        assert "<p>" not in result

    def test_fetch_url_strips_script_tags(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        html = "<html><body><script>var x=1;</script><p>Visible</p></body></html>"
        with patch(
            "devagent.tools.web_tools._fetch_url_response", return_value=_html_response(html)
        ):
            result = reg.call("fetch_url", {"url": "http://example.com"})
        assert "var x" not in result
        assert "Visible" in result

    def test_fetch_url_returns_plain_text_unchanged(self) -> None:
        from devagent.tools.web_tools import register_web_tools
        reg = _make_registry()
        register_web_tools(reg)
        with patch(
            "devagent.tools.web_tools._fetch_url_response",
            return_value=_text_response("raw text content"),
        ):
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
        with patch(
            "devagent.tools.web_tools._fetch_url_response",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = reg.call("fetch_url", {"url": "http://unreachable.invalid"})
        assert "[error]" in result

    def test_fetch_url_blocks_cloud_metadata_before_request(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response, register_web_tools

        reg = _make_registry()
        register_web_tools(reg)
        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: _record_request_response(
                requests, request, httpx.Response(200, text="metadata")
            )
        )
        fetch = lambda url: _fetch_url_response(url, transport=transport)
        with patch("devagent.tools.web_tools._fetch_url_response", side_effect=fetch):
            result = reg.call("fetch_url", {"url": "http://169.254.169.254/latest/meta-data/"})
        assert "[error]" in result
        assert requests == []

    def test_fetch_url_blocks_localhost_before_request(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response, register_web_tools

        reg = _make_registry()
        register_web_tools(reg)
        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: _record_request_response(
                requests, request, httpx.Response(200, text="private")
            )
        )
        fetch = lambda url: _fetch_url_response(url, transport=transport)
        with (
            patch("devagent.tools.web_tools._fetch_url_response", side_effect=fetch),
            patch(
                "devagent.tools.web_tools.socket.getaddrinfo",
                return_value=_addrinfo("127.0.0.1", 6379),
            ),
        ):
            result = reg.call("fetch_url", {"url": "http://localhost:6379/"})

        assert "[error]" in result
        assert requests == []

    def test_fetch_url_rejects_non_public_addresses_and_schemes(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        cases = [
            ("http://169.254.169.254/latest/meta-data/", None),
            ("http://127.0.0.1:6379/", None),
            ("http://[::1]:8080/admin", None),
            ("http://[fd00::1]/", None),
            ("http://[::a9fe:a9fe]/", None),
            ("http://[::ffff:169.254.169.254]/", None),
            ("http://[2002:a9fe:a9fe::]/", None),
            ("http://[2001:0000:4136:e378:8000:63bf:3fff:fdd2]/", None),
            ("http://[64:ff9b::a9fe:a9fe]/", None),
            ("http://localhost:6379/", ["127.0.0.1"]),
            ("http://mixed.example/", ["93.184.216.34", "10.0.0.8"]),
            ("http://nat64.example/", ["64:ff9b::a9fe:a9fe"]),
            ("file:///etc/passwd", None),
            ("http://user:password@example.com/", None),
        ]

        for url, resolved_addresses in cases:
            requests: list[httpx.Request] = []

            def respond(request: httpx.Request, seen=requests) -> httpx.Response:
                seen.append(request)
                return httpx.Response(200, text="reached")

            transport = httpx.MockTransport(respond)

            def resolve(
                host: str,
                port: int,
                addresses: list[str] | None = resolved_addresses,
                **_kwargs: object,
            ) -> list[tuple]:
                if addresses is None:
                    raise AssertionError(f"Unexpected DNS lookup for {host}")
                return [record for address in addresses for record in _addrinfo(address, port)]

            with (
                patch("devagent.tools.web_tools.socket.getaddrinfo", side_effect=resolve),
                pytest.raises(ValueError),
            ):
                _fetch_url_response(url, transport=transport)
            assert requests == [], url

    def test_fetch_url_rejects_invalid_dns_record_before_request(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: _record_request_response(
                requests, request, httpx.Response(200, text="reached")
            )
        )
        invalid_record = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (123, 80))

        with (
            patch("devagent.tools.web_tools.socket.getaddrinfo", return_value=[invalid_record]),
            pytest.raises(TypeError, match="invalid address"),
        ):
            _fetch_url_response("http://invalid-dns.example/", transport=transport)

        assert requests == []

    def test_fetch_url_pins_public_dns_result_and_preserves_host(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: _record_request_response(
                requests, request, httpx.Response(200, text="safe body")
            )
        )
        with patch(
            "devagent.tools.web_tools.socket.getaddrinfo",
            return_value=_addrinfo("93.184.216.34", 8080),
        ) as resolve:
            response = _fetch_url_response(
                "http://example.com:8080/path?query=value", transport=transport
            )

        assert response.text == "safe body"
        assert len(requests) == 1
        assert requests[0].url.host == "93.184.216.34"
        assert str(requests[0].url) == "http://93.184.216.34:8080/path?query=value"
        assert requests[0].headers["host"] == "example.com:8080"
        resolve.assert_called_once_with("example.com", 8080, type=socket.SOCK_STREAM)

    @pytest.mark.parametrize("error_type", ["connect", "timeout"])
    def test_fetch_url_falls_back_to_next_public_dns_result(self, error_type: str) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                error = (
                    httpx.ConnectError("connection refused", request=request)
                    if error_type == "connect"
                    else httpx.ConnectTimeout("connection timed out", request=request)
                )
                raise error
            return httpx.Response(200, text="fallback body")

        transport = httpx.MockTransport(respond)
        addresses = [_addrinfo("93.184.216.34", 80), _addrinfo("1.1.1.1", 80)]
        with patch(
            "devagent.tools.web_tools.socket.getaddrinfo",
            return_value=[record for result in addresses for record in result],
        ) as resolve:
            response = _fetch_url_response("http://example.com/path", transport=transport)

        assert response.text == "fallback body"
        assert [request.url.host for request in requests] == ["93.184.216.34", "1.1.1.1"]
        assert [request.headers["host"] for request in requests] == [
            "example.com",
            "example.com",
        ]
        resolve.assert_called_once_with("example.com", 80, type=socket.SOCK_STREAM)

    def test_fetch_url_ignores_environment_proxies(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        requests: list[httpx.Request] = []
        mock_transport = httpx.MockTransport(
            lambda request: _record_request_response(
                requests, request, httpx.Response(200, text="direct")
            )
        )
        real_client = httpx.Client
        client_options: list[tuple[httpx.BaseTransport | None, bool]] = []

        def make_client(
            *,
            transport: httpx.BaseTransport | None,
            timeout: float,
            follow_redirects: bool,
            trust_env: bool,
        ) -> httpx.Client:
            client_options.append((transport, trust_env))
            return real_client(
                transport=mock_transport,
                timeout=timeout,
                follow_redirects=follow_redirects,
                trust_env=trust_env,
            )

        with (
            patch("devagent.tools.web_tools.httpx.Client", side_effect=make_client),
            patch(
                "devagent.tools.web_tools.socket.getaddrinfo",
                return_value=_addrinfo("93.184.216.34", 443),
            ),
        ):
            response = _fetch_url_response("https://example.com/", transport=None)

        assert response.text == "direct"
        assert client_options == [(None, False)]
        assert len(requests) == 1

    def test_fetch_url_revalidates_each_redirect_and_keeps_tls_sni(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(302, headers={"location": "https://next.example.org/final"})
            return httpx.Response(200, text="redirected body")

        transport = httpx.MockTransport(respond)
        addresses = {"example.com": "93.184.216.34", "next.example.org": "1.1.1.1"}

        def resolve(host: str, port: int, **kwargs: object) -> list[tuple]:
            return _addrinfo(addresses[host], port)

        with patch("devagent.tools.web_tools.socket.getaddrinfo", side_effect=resolve) as resolver:
            response = _fetch_url_response("http://example.com/start", transport=transport)

        assert response.text == "redirected body"
        assert [request.url.host for request in requests] == ["93.184.216.34", "1.1.1.1"]
        assert [request.headers["host"] for request in requests] == [
            "example.com",
            "next.example.org",
        ]
        assert requests[1].extensions["sni_hostname"] == "next.example.org"
        assert [call.args[0] for call in resolver.call_args_list] == [
            "example.com",
            "next.example.org",
        ]

    def test_fetch_url_stops_redirect_to_private_dns_target(self) -> None:
        import httpx

        from devagent.tools.web_tools import _fetch_url_response

        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: (
                _record_request_response(
                    requests,
                    request,
                    httpx.Response(302, headers={"location": "http://internal.example/metadata"}),
                )
            )
        )

        def resolve(host: str, port: int, **kwargs: object) -> list[tuple]:
            address = "93.184.216.34" if host == "example.com" else "10.0.0.8"
            return _addrinfo(address, port)

        with (
            patch("devagent.tools.web_tools.socket.getaddrinfo", side_effect=resolve),
            pytest.raises(ValueError, match="non-public address"),
        ):
            _fetch_url_response("http://example.com/start", transport=transport)
        assert len(requests) == 1

    def test_fetch_url_limits_redirects(self) -> None:
        import httpx

        from devagent.tools.web_tools import _MAX_FETCH_REDIRECTS, _fetch_url_response

        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: (
                _record_request_response(
                    requests, request, httpx.Response(302, headers={"location": "/again"})
                )
            )
        )
        with (
            patch(
                "devagent.tools.web_tools.socket.getaddrinfo",
                return_value=_addrinfo("93.184.216.34", 80),
            ),
            pytest.raises(ValueError, match="Too many redirects"),
        ):
            _fetch_url_response("http://example.com/start", transport=transport)
        assert len(requests) == _MAX_FETCH_REDIRECTS + 1


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
