"""Session graph overlay — compact summary of what the agent has read/written.

Injected into the system prompt each turn so the LLM knows what context
it already has, preventing redundant re-reads and providing provenance.

Format (injected as a system message block):
  ## This Session (CodePrism)
  Read: devagent/core/llm.py::LLMClient, devagent/core/config.py::DevAgentConfig
  Wrote: devagent/tools/registry.py
  → Use cp_get_context / cp_search_symbol before reading raw files.
"""

from __future__ import annotations

from devagent.codeprism.client import CodePrismClient


_HEADER = "\n\n## This Session (CodePrism graph context)\n"
_FOOTER = (
    "\nPrefer cp_get_context / cp_search_symbol over read_file "
    "to save tokens when exploring the codebase."
)


def build_session_overlay(client: CodePrismClient) -> str:
    """Return the session overlay block to append to the system prompt.

    Returns empty string if CodePrism is not indexed or nothing was tracked yet.
    """
    if not client.is_indexed:
        return ""

    ctx = client.get_session_context()
    if not ctx:
        return ""

    reads = ctx.get("files_read", [])
    writes = ctx.get("files_written", [])

    if not reads and not writes:
        return ""

    lines = [_HEADER]
    if reads:
        short_reads = _truncate_list(reads, max_items=8)
        lines.append(f"Read ({len(reads)} total): {', '.join(short_reads)}")
    if writes:
        short_writes = _truncate_list(writes, max_items=5)
        lines.append(f"Wrote ({len(writes)} total): {', '.join(short_writes)}")

    lines.append(_FOOTER)
    return "\n".join(lines)


def _truncate_list(items: list[str], max_items: int) -> list[str]:
    if len(items) <= max_items:
        return items
    shown = items[:max_items]
    shown.append(f"... +{len(items) - max_items} more")
    return shown
