"""Tool registry -- maps tool names to handler callables.

All tools take a single dict of arguments and return a string result.
Tool definitions (for the LLM) are generated from registered entries.
"""

from __future__ import annotations

from typing import Any, Callable

from devagent.core.llm import ToolDef


ToolHandler = Callable[[dict[str, Any]], str]


class ToolRegistry:
    """Registry of all tools available to the agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: ToolHandler,
    ) -> None:
        self._tools[name] = ToolDef(name=name, description=description, parameters=parameters)
        self._handlers[name] = handler

    def get_definitions(self) -> list[ToolDef]:
        return list(self._tools.values())

    def call(self, name: str, args: dict[str, Any]) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"[tool_error] Unknown tool: {name!r}"
        try:
            return handler(args)
        except Exception as exc:
            return f"[tool_error] {name} failed: {exc}"

    def names(self) -> list[str]:
        return list(self._tools.keys())


def build_registry(project_root: str = ".") -> ToolRegistry:
    """Build and return the default tool registry with all built-in tools."""
    from devagent.tools.file_tools import register_file_tools
    from devagent.tools.shell_tool import register_shell_tool
    from devagent.tools.search_tools import register_search_tools
    from devagent.tools.git_tools import register_git_tools

    registry = ToolRegistry()
    register_file_tools(registry, project_root)
    register_shell_tool(registry, project_root)
    register_search_tools(registry, project_root)
    register_git_tools(registry, project_root)
    return registry
