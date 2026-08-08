"""MCP Client wrapper — connects to servers, calls tools with retry logic."""

from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession
from tenacity import retry, stop_after_attempt, wait_exponential


class ToolCallError(Exception):
    """Raised when an MCP tool call fails."""
    pass


class MCPClient:
    """Wrapper around mcp.ClientSession providing robust tool calling."""

    def __init__(self, session: ClientSession, server_name: str):
        self.session = session
        self.server_name = server_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server with retries.

        Returns the text content of the response.
        Raises ToolCallError if the tool call fails or returns an error.
        """
        try:
            result = await self.session.call_tool(tool_name, arguments)
            if result.isError:
                error_text = result.content[0].text if result.content else "Unknown error"
                raise ToolCallError(f"{self.server_name} tool '{tool_name}' failed: {error_text}")
            
            # Combine text from all content chunks
            text_content = ""
            if result.content:
                for content in result.content:
                    if content.type == "text":
                        text_content += content.text
            return text_content
        except Exception as exc:
            if not isinstance(exc, ToolCallError):
                raise ToolCallError(f"{self.server_name} tool '{tool_name}' exception: {exc}")
            raise
