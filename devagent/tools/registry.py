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


def build_registry(
    project_root: str = ".",
    codeprism_client=None,           # CodePrismClient | None
    security_log: list | None = None,
    confirm_fn=None,                 # Callable[[str], bool] | None
) -> ToolRegistry:
    """Build and return the default tool registry with all built-in tools.

    If codeprism_client is provided:
      - cp_* knowledge-graph tools are registered
      - write_file and edit_file are wrapped with the security gate

    security_log: caller-owned list that security gate appends events to.
    confirm_fn:   callable(warning_msg) -> bool; called on WARN-level issues.
                  If None, WARN proceeds without confirmation.
    """
    from devagent.tools.file_tools import register_file_tools
    from devagent.tools.shell_tool import register_shell_tool
    from devagent.tools.search_tools import register_search_tools
    from devagent.tools.git_tools import register_git_tools

    registry = ToolRegistry()
    register_file_tools(registry, project_root)
    register_shell_tool(registry, project_root)
    register_search_tools(registry, project_root)
    register_git_tools(registry, project_root)

    if codeprism_client is not None:
        from devagent.tools.codeprism_tools import register_codeprism_tools
        from devagent.tools.security_gate import wrap_write_with_security

        register_codeprism_tools(registry, codeprism_client)

        # Wrap file writers with impact estimation + security scanning
        for op in ("write_file", "edit_file"):
            original = registry._handlers.get(op)
            if original:
                registry._handlers[op] = wrap_write_with_security(
                    original,
                    codeprism_client,
                    project_root,
                    op.split("_")[0],
                    security_log=security_log,
                    confirm_fn=confirm_fn,
                )

    return registry
