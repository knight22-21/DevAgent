"""Typed client for the GitHub MCP server."""

from __future__ import annotations

import json

from specsync.mcp.client import MCPClient


class GitHubClient:
    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> dict:
        result = await self._client.call_tool("get_issue", {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number
        })
        return json.loads(result)

    async def get_file_contents(self, owner: str, repo: str, path: str, branch: str | None = None) -> str:
        args = {"owner": owner, "repo": repo, "path": path}
        if branch:
            args["branch"] = branch
        result = await self._client.call_tool("get_file_contents", args)
        return result

    async def search_code(self, query: str, owner: str, repo: str) -> dict:
        result = await self._client.call_tool("search_code", {
            "q": query,
            "owner": owner,
            "repo": repo
        })
        return json.loads(result)

    async def list_directory(self, owner: str, repo: str, path: str) -> dict:
        result = await self._client.call_tool("list_directory", {
            "owner": owner,
            "repo": repo,
            "path": path
        })
        return json.loads(result)
