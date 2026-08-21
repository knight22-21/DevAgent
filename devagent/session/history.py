"""Convert stored session events to AgentMessage lists for the LLM.

Handles the full set of roles: system, user, assistant (with tool calls), tool_result.
"""

from __future__ import annotations

from devagent.core.llm import AgentMessage, ToolCallRequest
from devagent.session import store


def build_messages(
    session_id: str,
    system_prompt: str,
    db_path=None,
) -> list[AgentMessage]:
    """Reconstruct the full conversation as AgentMessage objects.

    The system prompt is always first. Events are loaded from the DB
    and returned in chronological order with tool calls rehydrated.
    """
    events = store.get_events(session_id, db_path=db_path)

    messages: list[AgentMessage] = [
        AgentMessage(role="system", content=system_prompt)
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
