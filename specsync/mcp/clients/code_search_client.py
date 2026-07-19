"""Typed client for the CodeSearchMCP server."""

from __future__ import annotations

import json

from specsync.core.models import ConflictResult, IndexResult, SearchResult
from specsync.mcp.client import MCPClient


class CodeSearchClient:
    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client

    async def semantic_search(self, query: str, top_k: int = 5, filter_language: str | None = None) -> list[SearchResult]:
        args = {"query": query, "top_k": top_k}
        if filter_language:
            args["filter_language"] = filter_language
        result = await self._client.call_tool("semantic_search", args)
        data = json.loads(result)
        return [SearchResult(**res) for res in data]

    async def index_codebase(self, project_root: str, incremental: bool = True) -> IndexResult:
        result = await self._client.call_tool("index_codebase", {
            "project_root": project_root,
            "incremental": incremental
        })
        data = json.loads(result)
        return IndexResult(**data)

    async def get_import_graph(self, project_root: str) -> dict:
        result = await self._client.call_tool("get_import_graph", {
            "project_root": project_root
        })
        return json.loads(result)

    async def detect_conflicts(self, file_path: str, proposed_change_description: str) -> ConflictResult:
        result = await self._client.call_tool("detect_conflicts", {
            "file_path": file_path,
            "proposed_change_description": proposed_change_description
        })
        data = json.loads(result)
        return ConflictResult(**data)

    async def find_similar_implementations(self, description: str, exclude_files: list[str]) -> list[SearchResult]:
        result = await self._client.call_tool("find_similar_implementations", {
            "description": description,
            "exclude_files": exclude_files
        })
        data = json.loads(result)
        return [SearchResult(**res) for res in data]
