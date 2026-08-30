"""Convert stored session events to AgentMessage lists for the LLM.

Handles the full set of roles: system, user, assistant (with tool calls), tool_result.

Phase 8: When a compressed summary exists for a session, only the hot-window
events (is_compressed=0) are replayed.  The summary is appended to the system
prompt so the LLM retains context from earlier turns without paying the full
token cost of the original event log.
"""

from __future__ import annotations

from devagent.core.llm import AgentMessage, ToolCallRequest
from devagent.session import store


def build_messages(
    session_id: str,
    system_prompt: str,
    db_path=None,
) -> list[AgentMessage]:
    """Reconstruct the conversation as AgentMessage objects for the LLM.

    If a compressed summary exists the system prompt is augmented with it
    and only uncompressed (hot-window) events are replayed — reducing the
    number of tokens sent on every turn for long sessions.
    """
    compressed_summary = store.get_compressed_summary(session_id, db_path=db_path)

    if compressed_summary:
        # Inject summary into system prompt; load only the hot window
        full_system = (
            system_prompt
            + "\n\n## Context from earlier in this session (compressed summary):\n"
            + compressed_summary
        )
        events = store.get_active_events(session_id, db_path=db_path)
    else:
        full_system = system_prompt
        events = store.get_events(session_id, db_path=db_path)

    messages: list[AgentMessage] = [
        AgentMessage(role="system", content=full_system)
    ]

    for ev in events:
        role = ev["role"]
        content = ev["content"]
        raw_tool_calls = ev.get("tool_calls") or []

        if role == "tool_result":
            messages.append(AgentMessage(
                role="tool_result",
                content=content,
                tool_call_id=ev.get("tool_call_id", ""),
                tool_name=ev.get("tool_name", ""),
            ))
        elif role == "assistant":
            tool_calls = [
                ToolCallRequest(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    args=tc.get("args", {}),
                )
                for tc in raw_tool_calls
            ]
            messages.append(AgentMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            ))
        else:
            messages.append(AgentMessage(role=role, content=content))

    return messages


def estimate_tokens(messages: list[AgentMessage]) -> int:
    """Very rough token estimate: 1 token ~= 4 characters of text."""
    total = sum(len(m.content) for m in messages)
    return total // 4
