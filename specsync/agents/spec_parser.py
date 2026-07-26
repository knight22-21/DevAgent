"""SpecParserAgent: Parses specs into structured models."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from specsync.agents.state import PipelineState
from specsync.core.config import SpecSyncConfig
from specsync.mcp.manager import MCPManager


class SpecParserAgent:
    def __init__(self, config: SpecSyncConfig, mcp_manager: MCPManager):
        self.config = config
        self.mcp = mcp_manager
        
        # Build the graph
        workflow = StateGraph(PipelineState)
        workflow.add_node("search_context", self.search_context)
        workflow.add_node("parse_requirements", self.parse_requirements)
        workflow.add_node("infer_edge_cases", self.infer_edge_cases)
        workflow.add_node("extract_data_models", self.extract_data_models)
        workflow.add_node("identify_api_changes", self.identify_api_changes)

        workflow.add_edge(START, "search_context")
        workflow.add_edge("search_context", "parse_requirements")
        workflow.add_edge("parse_requirements", "infer_edge_cases")
        workflow.add_edge("parse_requirements", "extract_data_models")
        workflow.add_edge("parse_requirements", "identify_api_changes")
        
        workflow.add_edge("infer_edge_cases", END)
        workflow.add_edge("extract_data_models", END)
        workflow.add_edge("identify_api_changes", END)
        
        self.app = workflow.compile()

    async def search_context(self, state: PipelineState) -> dict:
        """Search the web for context if a search provider is configured."""
        query = f"Implementation patterns for: {state['spec_source']}"
        context = ""
        try:
            if self.config.search_provider == "brave" and self.mcp.brave:
                context = await self.mcp.brave.brave_web_search(query)
            elif self.config.search_provider == "searchx" and self.mcp.searchx:
                context = await self.mcp.searchx.searchx_web_search(query)
        except Exception:
            pass # Fail gracefully if search fails
            
        return {"search_context": context}

    async def parse_requirements(self, state: PipelineState) -> dict:
        """Parse raw spec text into atomic Requirement objects."""
        if not self.mcp.spec_analysis:
            raise RuntimeError("SpecAnalysisMCP server is not available.")

        reqs = await self.mcp.spec_analysis.parse_spec_to_requirements(
            spec_text=state["spec_text"],
            context=state.get("search_context", "")
        )
        return {"requirements": reqs}

    async def infer_edge_cases(self, state: PipelineState) -> dict:
        """Infer edge cases from the parsed requirements."""
        if not self.mcp.spec_analysis:
            return {"edge_cases": []}
            
        edge_cases = await self.mcp.spec_analysis.infer_edge_cases(
            requirements=state["requirements"],
            spec_text=state["spec_text"]
        )
        return {"edge_cases": edge_cases}

    async def extract_data_models(self, state: PipelineState) -> dict:
        """Extract implied data model changes."""
        if not self.mcp.spec_analysis:
            return {"data_models": []}
            
        data_models = await self.mcp.spec_analysis.extract_data_models(
            spec_text=state["spec_text"]
        )
        return {"data_models": data_models}

    async def identify_api_changes(self, state: PipelineState) -> dict:
        """Identify implied API changes."""
        if not self.mcp.spec_analysis:
            return {"api_changes": []}
            
        api_changes = await self.mcp.spec_analysis.identify_api_changes(
            spec_text=state["spec_text"]
        )
        return {"api_changes": api_changes}
