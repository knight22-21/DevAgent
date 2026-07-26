"""GapReportAgent: Estimates effort and generates the final report."""

from __future__ import annotations

import json
from pydantic import BaseModel, Field

from langgraph.graph import END, START, StateGraph

from specsync.agents.state import PipelineState
from specsync.core.config import SpecSyncConfig
from specsync.core.llm import get_llm_with_fallback
from specsync.core.models import (
    EffortEstimate,
    GapReport,
    RequirementAnalysis,
    RequirementStatus,
    RequirementType,
)


class AdjustedEstimate(BaseModel):
    conflict_resolution_hours: float
    extension_hours: float
    net_new_hours: float
    testing_hours: float
    confidence: str = Field(description="low, medium, high")
    notes: str


class ImplementationOrder(BaseModel):
    order: list[str] = Field(description="List of requirement IDs in recommended implementation order")


class GapReportAgent:
    def __init__(self, config: SpecSyncConfig):
        self.config = config
        self.llm = get_llm_with_fallback(config)
        
        workflow = StateGraph(PipelineState)
        workflow.add_node("estimate_effort", self.estimate_effort)
        workflow.add_node("determine_order", self.determine_order)
        workflow.add_node("generate_report", self.generate_report)

        workflow.add_edge(START, "estimate_effort")
        workflow.add_edge("estimate_effort", "determine_order")
        workflow.add_edge("determine_order", "generate_report")
        workflow.add_edge("generate_report", END)
        
        self.app = workflow.compile()

    def _apply_heuristics(self, analyses: list[RequirementAnalysis]) -> EffortEstimate:
        conflicts_h = 0.0
        extend_h = 0.0
        net_new_h = 0.0
        
        for ans in analyses:
            if ans.status == RequirementStatus.CONFLICTED:
                affected = len(ans.conflict_details.affected_files) if ans.conflict_details else 0
                if affected > 5:
                    conflicts_h += 6.0
                elif affected >= 2:
                    conflicts_h += 4.0
                else:
                    conflicts_h += 2.0
            elif ans.status == RequirementStatus.PARTIALLY_EXISTS:
                extend_h += 2.0
            elif ans.status == RequirementStatus.MISSING:
                rt = ans.requirement.requirement_type
                if rt == RequirementType.FEATURE:
                    net_new_h += 4.0
                elif rt == RequirementType.DATA_MODEL:
                    net_new_h += 1.0
                elif rt == RequirementType.API_CHANGE:
                    net_new_h += 2.0
                else:
                    net_new_h += 2.0  # default
                    
        subtotal = conflicts_h + extend_h + net_new_h
        testing_h = subtotal * 0.3
        total = subtotal + testing_h
        
        return EffortEstimate(
            conflict_resolution_hours=conflicts_h,
            extension_hours=extend_h,
            net_new_hours=net_new_h,
            testing_hours=testing_h,
            total_days=total / 8.0,
            confidence="medium",
            notes="Base heuristic estimate."
        )

    async def estimate_effort(self, state: PipelineState) -> dict:
        """Estimate effort using heuristics and LLM adjustment."""
        analyses = state.get("requirement_analyses", [])
        base_estimate = self._apply_heuristics(analyses)
        
        # Fast path: if no work needed, just return
        if base_estimate.total_days == 0:
            return {"effort_estimate": base_estimate}
            
        # Ask LLM to review
        analyses_dump = [a.model_dump() for a in analyses]
        prompt = (
            f"Review this heuristic effort estimate for the requirements.\n"
            f"Base Estimate: {base_estimate.model_dump_json(indent=2)}\n"
            f"Requirements Analysis:\n{json.dumps(analyses_dump, indent=2)}\n\n"
            f"Adjust the hours if necessary based on complexity, set confidence, and provide brief notes."
        )
        
        try:
            structured_llm = self.llm.with_structured_output(AdjustedEstimate)
            adj: AdjustedEstimate = await structured_llm.ainvoke(prompt)
            
            subtotal = adj.conflict_resolution_hours + adj.extension_hours + adj.net_new_hours
            testing = adj.testing_hours if adj.testing_hours > 0 else (subtotal * 0.3)
            
            final_estimate = EffortEstimate(
                conflict_resolution_hours=adj.conflict_resolution_hours,
                extension_hours=adj.extension_hours,
                net_new_hours=adj.net_new_hours,
                testing_hours=testing,
                total_days=(subtotal + testing) / 8.0,
                confidence=adj.confidence, # type: ignore
                notes=adj.notes
            )
            return {"effort_estimate": final_estimate}
        except Exception:
            return {"effort_estimate": base_estimate}

    async def determine_order(self, state: PipelineState) -> dict:
        """Determine implementation order using LLM."""
        analyses = state.get("requirement_analyses", [])
        if not analyses:
            return {"implementation_order": []}
            
        reqs = [{"id": a.requirement.id, "desc": a.requirement.description, "type": a.requirement.requirement_type} for a in analyses]
        prompt = (
            f"Given these requirements, determine the optimal implementation order.\n"
            f"Generally, data models come first, then APIs, then features.\n"
            f"Requirements:\n{json.dumps(reqs, indent=2)}\n\n"
            f"Return ONLY the ordered list of IDs."
        )
        
        try:
            structured_llm = self.llm.with_structured_output(ImplementationOrder)
            result: ImplementationOrder = await structured_llm.ainvoke(prompt)
            return {"implementation_order": result.order}
        except Exception:
            # Fallback to naive sort
            return {"implementation_order": [r["id"] for r in reqs]}

    async def generate_report(self, state: PipelineState) -> dict:
        """Compile all information into the final GapReport."""
        analyses = state.get("requirement_analyses", [])
        
        reuse = [a for a in analyses if a.status == RequirementStatus.FULLY_EXISTS]
        extend = [a for a in analyses if a.status == RequirementStatus.PARTIALLY_EXISTS]
        conflicts = [a for a in analyses if a.status == RequirementStatus.CONFLICTED]
        net_new = [a for a in analyses if a.status == RequirementStatus.MISSING]
        
        estimate = state.get("effort_estimate")
        if not estimate:
            estimate = self._apply_heuristics(analyses)
            
        report = GapReport(
            spec_source=state.get("spec_source", "Unknown"),
            reuse=reuse,
            extend=extend,
            conflicts=conflicts,
            net_new=net_new,
            edge_cases=state.get("edge_cases", []),
            data_models=state.get("data_models", []),
            api_changes=state.get("api_changes", []),
            implementation_order=state.get("implementation_order", []),
            effort_estimate=estimate
        )
        return {"gap_report": report}
