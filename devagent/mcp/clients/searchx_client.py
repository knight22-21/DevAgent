"""Typed client for the SearchX MCP server."""

from __future__ import annotations

from devagent.mcp.client import MCPClient


class SearchXClient:
    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client

    async def searchx_web_search(self, query: str, count: int = 3) -> str:
        """Search the web using SearchX. Returns the raw result string."""
        return await self._client.call_tool("searchx_web_search", {
            "query": query,
            "count": count
        })
