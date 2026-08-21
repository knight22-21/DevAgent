"""Memory tools — expose MemoryBlock as agent-callable tools.

The agent can call remember_fact / recall_facts / forget_fact to maintain
a structured, token-bounded fact store across turns rather than re-reading
the full conversation history to recover previously discovered context.
"""

from __future__ import annotations

from devagent.tools.registry import ToolRegistry


def register_memory_tools(registry: ToolRegistry, memory_block) -> None:
    """Register remember_fact, recall_facts, and forget_fact tools."""

    def _remember_fact(args: dict) -> str:
        key = str(args.get("key", "")).strip()
        value = str(args.get("value", "")).strip()
        if not key:
            return "[error] remember_fact: 'key' is required"
        if not value:
            return "[error] remember_fact: 'value' is required"
        memory_block.set(key, value)
        return f"[remembered] {key}"

    def _recall_facts(args: dict) -> str:
        items = memory_block.all()
        if not items:
            return "[memory] No facts stored in this session."
        return "\n".join(f"- {k}: {v}" for k, v in sorted(items.items()))

    def _forget_fact(args: dict) -> str:
        key = str(args.get("key", "")).strip()
        if not key:
            return "[error] forget_fact: 'key' is required"
        memory_block.delete(key)
        return f"[forgotten] {key}"

    registry.register(
        "remember_fact",
        (
            "Store a key-value fact in session memory. Use this to persist important context "
            "across turns: decisions made, files explored, patterns discovered, or any insight "
            "worth keeping. Memory is injected into your system prompt each turn (~200 tokens max). "
            "Prefer concise values (under 100 tokens). Overwrite a key to update a fact."
        ),
        {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Short snake_case identifier (e.g. 'auth_module', 'test_command')",
                },
                "value": {
                    "type": "string",
                    "description": "The fact content, concise (preferably under 100 tokens)",
                },
            },
            "required": ["key", "value"],
        },
        _remember_fact,
    )

    registry.register(
        "recall_facts",
        "List all facts currently stored in session memory.",
        {"type": "object", "properties": {}},
        _recall_facts,
    )

    registry.register(
        "forget_fact",
        "Remove a stored fact from session memory by its key.",
        {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The key to remove",
                },
            },
            "required": ["key"],
        },
        _forget_fact,
    )
