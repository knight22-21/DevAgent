"""WebSocket connection manager for live session event streaming.

Usage:
    from devagent.server.ws_manager import manager

    # In an async WebSocket endpoint:
    await manager.connect(session_id, websocket)
    await manager.publish(session_id, {"type": "event", ...})
    await manager.disconnect(session_id, websocket)

    # From sync code (agent loop threads):
    manager.publish_nowait(session_id, message, event_loop)
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Thread-safe registry of active WebSocket connections, keyed by session_id."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        """Accept and register a WebSocket for a session."""
        await ws.accept()
        async with self._lock:
            self._connections[session_id].append(ws)

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        """Remove a WebSocket from the registry."""
        async with self._lock:
            try:
                self._connections[session_id].remove(ws)
            except ValueError:
                pass

    async def publish(self, session_id: str, message: dict[str, Any]) -> None:
        """Push a JSON message to every subscriber of session_id.

        Dead connections are silently removed.
        """
        text = json.dumps(message, default=str)
        async with self._lock:
            sockets = list(self._connections.get(session_id, []))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    try:
                        self._connections[session_id].remove(ws)
                    except ValueError:
                        pass

    def publish_nowait(
        self,
        session_id: str,
        message: dict[str, Any],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Thread-safe fire-and-forget publish from synchronous code.

        Call this from the agent loop (which runs in a ThreadPoolExecutor)
        to push events to WebSocket clients without blocking.
        """
        asyncio.run_coroutine_threadsafe(self.publish(session_id, message), loop)

    def active_count(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Global singleton — imported by fastapi_app.py and future publishers
manager = ConnectionManager()
