"""LangGraph state definition for the agent pipeline."""

from __future__ import annotations

from typing import TypedDict

from devagent.core.models import (
    APIChange,
    DataModel,
    EdgeCase,
    EffortEstimate,
    GapReport,
    Requirement,
    RequirementAnalysis,
)


class PipelineState(TypedDict):
    """The state dictionary passed through the LangGraph agents."""
    # Inputs
    spec_text: str
    spec_source: str

    # SpecParserAgent outputs
    search_context: str
    requirements: list[Requirement]
    edge_cases: list[EdgeCase]
    data_models: list[DataModel]
    api_changes: list[APIChange]

    # CodeInventoryAgent outputs
    requirement_analyses: list[RequirementAnalysis]

    # GapReportAgent outputs
    effort_estimate: EffortEstimate | None
    implementation_order: list[str]
    gap_report: GapReport | None
