"""Typed client for the Brave Search MCP server."""

from __future__ import annotations

import json

from devagent.mcp.client import MCPClient


class BraveClient:
    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client

    async def brave_web_search(self, query: str, count: int = 3) -> str:
        """Search the web using Brave Search. Returns the raw result string."""
        return await self._client.call_tool("brave_web_search", {
            "query": query,
            "count": count
        })
