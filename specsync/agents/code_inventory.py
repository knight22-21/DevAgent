"""CodeInventoryAgent: Searches codebase and classifies requirement status."""

from __future__ import annotations

import asyncio
from pydantic import BaseModel, Field

from langgraph.graph import END, START, StateGraph

from specsync.agents.state import PipelineState
from specsync.core.config import SpecSyncConfig
from specsync.core.llm import get_llm_with_fallback
from specsync.core.models import (
    ConflictResult,
    Requirement,
    RequirementAnalysis,
    RequirementStatus,
)
from specsync.mcp.manager import MCPManager


class RequirementClassification(BaseModel):
    """Structured output expected from the LLM when classifying a requirement."""
    status: RequirementStatus = Field(description="The status of the requirement in the current codebase.")
    matched_files: list[str] = Field(description="Files that contain relevant implementation.")
    matched_functions: list[str] = Field(description="Functions or classes that contain relevant implementation.")
    conflict_severity: str | None = Field(description="high, medium, or low if CONFLICTED, otherwise null")
    conflict_explanation: str | None = Field(description="Explanation of the conflict if applicable")
    classification_reason: str = Field(description="Why this status was chosen.")


class CodeInventoryAgent:
    def __init__(self, config: SpecSyncConfig, mcp_manager: MCPManager, project_root: str):
        self.config = config
        self.mcp = mcp_manager
        self.project_root = project_root
        self.llm = get_llm_with_fallback(config)
        self._search_results_cache: list[tuple[Requirement, list]] = []

        workflow = StateGraph(PipelineState)
        workflow.add_node("search_requirements", self.search_requirements)
        workflow.add_node("classify_requirements", self.classify_requirements)

        workflow.add_edge(START, "search_requirements")
        workflow.add_edge("search_requirements", "classify_requirements")
        workflow.add_edge("classify_requirements", END)

        self.app = workflow.compile()

    async def search_requirements(self, state: PipelineState) -> dict:
        """Search the codebase for all requirements in parallel."""
        if not self.mcp.code_search:
            raise RuntimeError("CodeSearchMCP server is not available.")

        reqs = state.get("requirements", [])

        # Parallel search
        async def search_one(req: Requirement) -> tuple[Requirement, list]:
            results = await self.mcp.code_search.semantic_search(
                query=req.description,
                project_root=self.project_root,
                top_k=5
            )
            return req, results

        search_tasks = [search_one(req) for req in reqs]
        search_results_pairs = await asyncio.gather(*search_tasks)

        # Cache in instance variable to avoid LangGraph state merging issues
        self._search_results_cache = search_results_pairs
        return {}

    async def classify_requirements(self, state: PipelineState) -> dict:
        """Classify each requirement based on search results."""
        # Use instance cache instead of state to avoid LangGraph merging issues
        search_results_pairs = self._search_results_cache
        analyses: list[RequirementAnalysis] = []

        # Use structured output
        # For Ollama, we might need a specific prompt wrapper, but langchain handles this usually.
        # Fallback to json mode if needed, but with_structured_output is standard.
        try:
            structured_llm = self.llm.with_structured_output(RequirementClassification)
        except NotImplementedError:
            # Fallback if provider doesn't support it perfectly natively (e.g. some older models)
            # But the spec says to use with_structured_output.
            structured_llm = self.llm.with_structured_output(RequirementClassification)

        # Process sequentially to avoid blowing up LLM rate limits/context window
        for req, results in search_results_pairs:
            # Format results into a readable context
            context_str = "\n---\n".join([
                f"File: {r.file_path}\nType: {r.chunk_type}\nName: {r.name}\nSimilarity: {r.similarity_score:.2f}\nCode:\n{r.content}"
                for r in results
            ])

            prompt = (
                f"Analyze the following requirement against the codebase search results.\n"
                f"Requirement ID: {req.id}\n"
                f"Description: {req.description}\n"
                f"Type: {req.requirement_type}\n\n"
                f"Search Results:\n{context_str if context_str else 'No results found.'}\n\n"
                f"Classify the status. Be strict. If code doesn't exist, it is MISSING."
            )

            try:
                classification: RequirementClassification = await structured_llm.ainvoke(prompt)

                conflict_details = None
                if classification.status == RequirementStatus.CONFLICTED and classification.conflict_severity:
                    conflict_details = ConflictResult(
                        affected_files=classification.matched_files,
                        conflict_severity=classification.conflict_severity, # type: ignore
                        explanation=classification.conflict_explanation or ""
                    )

                analysis = RequirementAnalysis(
                    requirement=req,
                    status=classification.status,
                    matched_files=classification.matched_files,
                    matched_functions=classification.matched_functions,
                    conflict_details=conflict_details,
                    classification_reason=classification.classification_reason
                )
                analyses.append(analysis)
            except Exception as e:
                # Fallback on error
                analyses.append(RequirementAnalysis(
                    requirement=req,
                    status=RequirementStatus.MISSING,
                    matched_files=[],
                    matched_functions=[],
                    classification_reason=f"Failed to classify: {str(e)}"
                ))

        return {"requirement_analyses": analyses}
