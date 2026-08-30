"""Explicit plan mode — generate a structured plan before execution.

The planner calls the LLM once with a planning-only prompt and asks it to
return a JSON plan via a submit_plan tool call. The plan is then displayed
to the user for approval before any code is executed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class PlanStep:
    number: int
    description: str
    tool_hints: list[str] = field(default_factory=list)
    estimated_tokens: int = 0


@dataclass
class Plan:
    task: str
    steps: list[PlanStep]
    estimated_tool_calls: int = 0
    estimated_tokens: int = 0


_PLANNING_SYSTEM = """\
You are a planning assistant for an AI coding agent. Your job is to produce a clear,
step-by-step plan for a given coding task — nothing else. Do not write code or make
any changes. Only produce the plan.

Call the submit_plan tool with your plan as structured JSON.
The plan should have 3–8 steps. Each step should be concrete and actionable.
tool_hints are the tool names the agent will likely use in that step (optional).
estimated_tokens is a rough estimate of tokens that step will consume (optional).
"""

_SUBMIT_PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the structured plan. Call this exactly once.",
    "parameters": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer"},
                        "description": {"type": "string"},
                        "tool_hints": {"type": "array", "items": {"type": "string"}},
                        "estimated_tokens": {"type": "integer"},
                    },
                    "required": ["number", "description"],
                },
            },
            "estimated_tool_calls": {"type": "integer"},
            "estimated_tokens": {"type": "integer"},
        },
        "required": ["steps"],
    },
}


def generate_plan(llm, task: str, project_name: str) -> Plan:
    """Call LLM to generate a structured plan for the given task.

    Uses the LLMClient.complete_with_tools API with a planning-only tool.
    Falls back gracefully if the LLM returns text instead of a tool call.
    """
    from devagent.core.llm import ToolDef

    planning_tool = ToolDef(
        name=_SUBMIT_PLAN_TOOL["name"],
        description=_SUBMIT_PLAN_TOOL["description"],
        parameters=_SUBMIT_PLAN_TOOL["parameters"],
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                f"Project: {project_name}\n\n"
                "Produce a step-by-step plan for this task. Call submit_plan with your plan."
            ),
        }
    ]

    try:
        response = llm.complete_with_tools(
            messages,
            [planning_tool],
            system=_PLANNING_SYSTEM,
        )
    except TypeError:
        # Older LLMClient signature without system kwarg — try without it
        try:
            response = llm.complete_with_tools(messages, [planning_tool])
        except Exception:
            return _fallback_plan(task)
    except Exception:
        return _fallback_plan(task)

    # Happy path: LLM called submit_plan
    if response.has_tool_calls:
        for tc in response.tool_calls:
            if tc.name == "submit_plan":
                return _parse_plan(task, tc.args)

    # Fallback: LLM returned text — try to parse as JSON
    if response.content:
        try:
            data = json.loads(response.content)
            return _parse_plan(task, data)
        except Exception:
            pass

    return _fallback_plan(task)


def _parse_plan(task: str, data: dict) -> Plan:
    steps = []
    for raw in data.get("steps", []):
        steps.append(PlanStep(
            number=int(raw.get("number", len(steps) + 1)),
            description=str(raw.get("description", "")),
            tool_hints=list(raw.get("tool_hints", [])),
            estimated_tokens=int(raw.get("estimated_tokens", 0)),
        ))
    return Plan(
        task=task,
        steps=steps,
        estimated_tool_calls=int(data.get("estimated_tool_calls", 0)),
        estimated_tokens=int(data.get("estimated_tokens", 0)),
    )


def _fallback_plan(task: str) -> Plan:
    """Minimal single-step plan when LLM planning fails."""
    return Plan(
        task=task,
        steps=[
            PlanStep(number=1, description=f"Execute: {task}"),
        ],
    )
