"""Typed client for the Filesystem MCP server."""

from __future__ import annotations

import json

from specsync.mcp.client import MCPClient


class FilesystemClient:
    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client

    async def read_file(self, path: str) -> str:
        result = await self._client.call_tool("read_file", {"path": path})
        return result

    async def list_directory(self, path: str) -> list[str]:
        result = await self._client.call_tool("list_directory", {"path": path})
        # Note: Depending on the MCP server implementation, this might be JSON or plain text.
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result.splitlines()

    async def search_files(self, path: str, pattern: str) -> list[str]:
        result = await self._client.call_tool("search_files", {"path": path, "pattern": pattern})
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result.splitlines()
