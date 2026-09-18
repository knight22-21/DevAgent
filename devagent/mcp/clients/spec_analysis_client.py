"""Typed client for the SpecAnalysisMCP server."""

from __future__ import annotations

import json

from devagent.core.models import APIChange, DataModel, EdgeCase, Requirement
from devagent.mcp.client import MCPClient


class SpecAnalysisClient:
    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client

    async def parse_spec_to_requirements(self, spec_text: str, context: str = "") -> list[Requirement]:
        result = await self._client.call_tool("parse_spec_to_requirements", {
            "spec_text": spec_text,
            "context": context
        })
        data = json.loads(result)
        return [Requirement(**req) for req in data]

    async def infer_edge_cases(self, requirements: list[Requirement], spec_text: str) -> list[EdgeCase]:
        req_dicts = [req.model_dump() for req in requirements]
        result = await self._client.call_tool("infer_edge_cases", {
            "requirements": req_dicts,
            "spec_text": spec_text
        })
        data = json.loads(result)
        return [EdgeCase(**ec) for ec in data]

    async def extract_data_models(self, spec_text: str) -> list[DataModel]:
        result = await self._client.call_tool("extract_data_models", {
            "spec_text": spec_text
        })
        data = json.loads(result)
        return [DataModel(**dm) for dm in data]

    async def identify_api_changes(self, spec_text: str) -> list[APIChange]:
        result = await self._client.call_tool("identify_api_changes", {
            "spec_text": spec_text
        })
        data = json.loads(result)
        return [APIChange(**ac) for ac in data]
