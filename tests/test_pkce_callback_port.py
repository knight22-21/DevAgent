"""The OAuth redirect port must not be free between picking it and listening on it.

``_find_free_port`` bound a socket, read the port and closed it again, so anything on the
machine could claim that port before the callback server bound it -- the redirect from the
browser then landed on a port nothing was listening on. The flow now binds the socket once
and hands it to the server, so the port is never released in between.

Offline: loopback sockets only, no browser and no network beyond 127.0.0.1.
"""

from __future__ import annotations

import socket
import urllib.parse
import urllib.request

import pytest

from devagent.mcp.auth import pkce


def _probe_bind(port: int) -> None:
    """Try to take *port* the way an unrelated process would, without round trips."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
    finally:
        probe.close()


def _nothing_is_listening(port: int) -> bool:
    """Whether a fresh connection to *port* is refused, i.e. no server holds it.

    A refused connection is the fact under test -- once the flow returns (or once
    ``server_close()`` has run) nothing may be listening on the callback port.
    Probing with a ``bind`` measures something else, and on Linux it measures it
    wrongly: the port is also unbindable -- even with ``SO_REUSEADDR`` -- while the
    connection the last run accepted lingers (the client never closed its end), and
    that is not the server still holding the port. A connect to a port with no
    listener is refused whatever state the old connection is in, on either OS.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return False
    except OSError:
        return True


class TestThePortIsHeld:
    def test_another_socket_cannot_take_the_port(self) -> None:
        sock = pkce._bind_callback_socket()
        try:
            port = sock.getsockname()[1]
            with pytest.raises(OSError):
                _probe_bind(port)
        finally:
            sock.close()

    def test_the_callback_server_serves_on_the_same_socket(self) -> None:
        sock = pkce._bind_callback_socket()
        port = sock.getsockname()[1]
        server, result = pkce._start_callback_server(sock)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/callback?code=abc", timeout=5
            ) as resp:
                body = resp.read()
                status = resp.status
            assert status == 200
            assert b"Authorization complete" in body
            assert result.code == "abc"
            assert result.error == ""
            assert result.done.is_set()
        finally:
            server.shutdown()
            server.server_close()

    def test_an_oauth_error_is_captured_too(self) -> None:
        sock = pkce._bind_callback_socket()
        port = sock.getsockname()[1]
        server, result = pkce._start_callback_server(sock)
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/callback?error=access_denied", timeout=5
            ).read()
            assert result.error == "access_denied"
            assert result.code == ""
        finally:
            server.shutdown()
            server.server_close()

    def test_closing_the_server_releases_the_port(self) -> None:
        sock = pkce._bind_callback_socket()
        port = sock.getsockname()[1]
        server, _ = pkce._start_callback_server(sock)
        server.shutdown()
        server.server_close()

        assert _nothing_is_listening(port)


class TestTheFlowUsesThatSocket:
    def test_the_redirect_uri_points_at_the_listening_port(self, monkeypatch) -> None:
        """The browser's redirect has to reach the server the flow just started."""
        seen: dict[str, str] = {}

        def fake_open(url: str) -> None:
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
            seen["redirect_uri"] = query["redirect_uri"]
            # stand in for the browser following the provider's redirect
            with urllib.request.urlopen(f"{query['redirect_uri']}?code=CODE123", timeout=5) as resp:
                resp.read()

        def fake_exchange(token_url, client_id, code, verifier, redirect_uri):
            return {"access_token": "t", "code": code, "redirect_uri": redirect_uri}

        monkeypatch.setattr(pkce.webbrowser, "open", fake_open)
        monkeypatch.setattr(pkce, "_exchange_code", fake_exchange)

        tokens = pkce.pkce_authorize(
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            client_id="devagent",
            scopes=["mcp.read"],
            timeout=10,
        )

        assert tokens["code"] == "CODE123"
        assert tokens["redirect_uri"] == seen["redirect_uri"]
        assert seen["redirect_uri"].startswith("http://127.0.0.1:")

    def test_the_port_is_released_when_the_flow_ends(self, monkeypatch) -> None:
        held: dict[str, int] = {}

        def fake_open(url: str) -> None:
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
            held["port"] = int(urllib.parse.urlparse(query["redirect_uri"]).port)
            with urllib.request.urlopen(f"{query['redirect_uri']}?code=C", timeout=5) as resp:
                resp.read()

        monkeypatch.setattr(pkce.webbrowser, "open", fake_open)
        monkeypatch.setattr(pkce, "_exchange_code", lambda *a, **k: {"access_token": "t"})

        pkce.pkce_authorize(
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            client_id="devagent",
            scopes=["mcp.read"],
            timeout=10,
        )

        assert _nothing_is_listening(held["port"])
