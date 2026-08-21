"""ReAct agent loop.

Drives the Reason + Act cycle:
  1. Build messages from history
  2. Call LLM (with tools)
  3. If the LLM requests tool calls, execute them and loop
  4. If the LLM produces a final text response, yield it and stop

The loop is a sync generator that yields AgentEvent objects so the
caller (CLI) can stream output while driving the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generator, Any

from devagent.core.llm import AgentMessage, LLMClient, ToolCallRequest
from devagent.session.budget import TokenBudget, BudgetExceeded
from devagent.session.history import build_messages
from devagent.session.manager import SessionManager
from devagent.session.memory import MemoryBlock
from devagent.tools.registry import ToolRegistry


MAX_ITERATIONS = 30  # hard safety cap


# ---------------------------------------------------------------------------
# Event types emitted by the loop
# ---------------------------------------------------------------------------

@dataclass
class ThinkingEvent:
    """LLM produced reasoning text before (or without) tool calls."""
    text: str


@dataclass
class ToolCallEvent:
    """LLM is calling a tool."""
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResultEvent:
    """Tool execution completed."""
    id: str
    name: str
    result: str
    success: bool = True


@dataclass
class FinalAnswerEvent:
    """LLM has produced a final text answer (no more tool calls)."""
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class BudgetWarningEvent:
    """Token budget is running low."""
    used: int
    remaining: int | None
    limit: int | None


@dataclass
class ErrorEvent:
    """Unrecoverable error."""
    message: str


AgentEvent = (
    ThinkingEvent
    | ToolCallEvent
    | ToolResultEvent
    | FinalAnswerEvent
    | BudgetWarningEvent
    | ErrorEvent
)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        session_mgr: SessionManager,
        session_id: str,
        memory: MemoryBlock,
        budget: TokenBudget,
        system_prompt: str,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.session_mgr = session_mgr
        self.session_id = session_id
        self.memory = memory
        self.budget = budget
        self.system_prompt = system_prompt

    def run(self, user_message: str) -> Generator[AgentEvent, None, None]:
        """Drive one user turn through the ReAct loop.

        Yields AgentEvents as they happen. The caller consumes and renders them.
        """
        # Persist user message
        self.session_mgr.record_user(self.session_id, user_message)

        tools = self.registry.get_definitions()
        iteration = 0

        # Reload full system prompt with latest memory
        memory_block = self.memory.as_prompt_block()
        full_system = self.system_prompt
        if memory_block:
            full_system = full_system + memory_block

        while iteration < MAX_ITERATIONS:
            iteration += 1

            # Build message history from DB
            messages = build_messages(self.session_id, full_system)

            # Budget check
            try:
                self.budget.check()
            except BudgetExceeded as exc:
                yield ErrorEvent(str(exc))
                return

            # LLM call
            try:
                response = self.llm.complete_with_tools(messages, tools)
            except Exception as exc:
                yield ErrorEvent(f"LLM error: {exc}")
                return

            # Record token usage
            self.budget.record(response.input_tokens, response.output_tokens)

            # Check budget warning threshold
            threshold = self.budget.warn_threshold
            if threshold and self.budget.max_tokens:
                frac = self.budget.total_used / self.budget.max_tokens
                if frac >= threshold:
                    yield BudgetWarningEvent(
                        used=self.budget.total_used,
                        remaining=self.budget.remaining,
                        limit=self.budget.max_tokens,
                    )

            # Emit thinking text if any
            if response.content:
                yield ThinkingEvent(response.content)

            if response.has_tool_calls:
                # Persist the assistant message with tool calls
                self.session_mgr.record_assistant(
                    self.session_id,
                    content=response.content,
                    tool_calls=[
                        {"id": tc.id, "name": tc.name, "args": tc.args}
                        for tc in response.tool_calls
                    ],
                    tokens_in=response.input_tokens,
                    tokens_out=response.output_tokens,
                )

                # Execute each tool call
                for tc in response.tool_calls:
                    yield ToolCallEvent(id=tc.id, name=tc.name, args=tc.args)

                    result = self.registry.call(tc.name, tc.args)
                    success = not result.startswith("[error]") and not result.startswith("[blocked]")

                    yield ToolResultEvent(id=tc.id, name=tc.name, result=result, success=success)

                    # Persist tool result
                    self.session_mgr.record_tool_result(
                        self.session_id,
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        content=result,
                    )

                # Loop back to let the LLM continue
                continue

            else:
                # Final answer -- no more tool calls
                self.session_mgr.record_assistant(
                    self.session_id,
                    content=response.content,
                    tokens_in=response.input_tokens,
                    tokens_out=response.output_tokens,
                )
                yield FinalAnswerEvent(
                    text=response.content,
                    tokens_in=response.input_tokens,
                    tokens_out=response.output_tokens,
                )
                return

        # Exceeded max iterations
        yield ErrorEvent(f"Agent loop exceeded {MAX_ITERATIONS} iterations without finishing")
