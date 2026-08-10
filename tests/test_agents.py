import pytest
from unittest.mock import AsyncMock, MagicMock
from devagent.agents.state import PipelineState
from devagent.core.config import DevAgentConfig
from devagent.core.models import Requirement, RequirementType

from devagent.agents.spec_parser import SpecParserAgent
from devagent.agents.code_inventory import CodeInventoryAgent
from devagent.agents.gap_report import GapReportAgent

@pytest.fixture
def mock_config():
    config = DevAgentConfig()
    config.search_provider = "searchx"
    return config

@pytest.fixture
def mock_mcp_manager():
    manager = MagicMock()
    
    # Mock SpecAnalysisClient
    sa_client = AsyncMock()
    req = Requirement(
        id="REQ-1",
        description="Test desc",
        requirement_type=RequirementType.FEATURE,
        priority="high",
        raw_text="raw"
    )
    sa_client.parse_spec_to_requirements.return_value = [req]
    sa_client.infer_edge_cases.return_value = []
    sa_client.extract_data_models.return_value = []
    sa_client.identify_api_changes.return_value = []
    
    # Mock CodeSearchClient
    cs_client = AsyncMock()
    cs_client.semantic_search.return_value = []
    
    manager.spec_analysis = sa_client
    manager.code_search = cs_client
    manager.brave = None
    manager.searchx = None
    
    return manager

@pytest.mark.asyncio
async def test_spec_parser_agent(mock_config, mock_mcp_manager):
    agent = SpecParserAgent(mock_config, mock_mcp_manager)
    
    initial_state: PipelineState = {
        "spec_text": "Need a test feature",
        "spec_source": "test",
        "search_context": "",
        "requirements": [],
        "edge_cases": [],
        "data_models": [],
        "api_changes": [],
        "requirement_analyses": [],
        "effort_estimate": None,
        "implementation_order": [],
        "gap_report": None
    }
    
    result = await agent.app.ainvoke(initial_state)
    
    assert len(result["requirements"]) == 1
    assert result["requirements"][0].id == "REQ-1"

@pytest.mark.asyncio
async def test_code_inventory_agent(mock_config, mock_mcp_manager, monkeypatch):
    # Mock LLM structured output inside CodeInventoryAgent
    class MockLLM:
        def with_structured_output(self, *args, **kwargs):
            class MockStructured:
                async def ainvoke(self, *a, **k):
                    from devagent.agents.code_inventory import RequirementClassification
                    from devagent.core.models import RequirementStatus
                    return RequirementClassification(
                        status=RequirementStatus.MISSING,
                        matched_files=[],
                        matched_functions=[],
                        conflict_severity=None,
                        conflict_explanation=None,
                        classification_reason="No code found"
                    )
            return MockStructured()
            
    monkeypatch.setattr("devagent.agents.code_inventory.get_llm_with_fallback", lambda config: MockLLM())
    
    agent = CodeInventoryAgent(mock_config, mock_mcp_manager, "/test/path")
    
    req = Requirement(
        id="REQ-1",
        description="Test desc",
        requirement_type=RequirementType.FEATURE,
        priority="high",
        raw_text="raw"
    )
    
    initial_state: PipelineState = {
        "spec_text": "",
        "spec_source": "",
        "search_context": "",
        "requirements": [req],
        "edge_cases": [],
        "data_models": [],
        "api_changes": [],
        "requirement_analyses": [],
        "effort_estimate": None,
        "implementation_order": [],
        "gap_report": None
    }
    
    result = await agent.app.ainvoke(initial_state)
    
    analyses = result["requirement_analyses"]
    assert len(analyses) == 1
    assert analyses[0].status.value == "MISSING"

@pytest.mark.asyncio
async def test_gap_report_agent(mock_config, monkeypatch):
    class MockLLM:
        def with_structured_output(self, schema, *args, **kwargs):
            class MockStructured:
                async def ainvoke(self, *a, **k):
                    if schema.__name__ == "AdjustedEstimate":
                        from devagent.agents.gap_report import AdjustedEstimate
                        return AdjustedEstimate(
                            conflict_resolution_hours=0.0,
                            extension_hours=0.0,
                            net_new_hours=5.0,
                            testing_hours=1.5,
                            confidence="high",
                            notes="Test notes"
                        )
                    else:
                        from devagent.agents.gap_report import ImplementationOrder
                        return ImplementationOrder(order=["REQ-1"])
            return MockStructured()
            
    monkeypatch.setattr("devagent.agents.gap_report.get_llm_with_fallback", lambda config: MockLLM())
    
    agent = GapReportAgent(mock_config)
    
    from devagent.core.models import RequirementAnalysis, RequirementStatus
    req = Requirement(
        id="REQ-1",
        description="Test desc",
        requirement_type=RequirementType.FEATURE,
        priority="high",
        raw_text="raw"
    )
    analysis = RequirementAnalysis(
        requirement=req,
        status=RequirementStatus.MISSING,
        matched_files=[],
        matched_functions=[],
        classification_reason="Missing"
    )
    
    initial_state: PipelineState = {
        "spec_text": "",
        "spec_source": "",
        "search_context": "",
        "requirements": [req],
        "edge_cases": [],
        "data_models": [],
        "api_changes": [],
        "requirement_analyses": [analysis],
        "effort_estimate": None,
        "implementation_order": [],
        "gap_report": None
    }
    
    result = await agent.app.ainvoke(initial_state)
    
    report = result["gap_report"]
    assert report is not None
    assert len(report.net_new) == 1
    assert report.effort_estimate.net_new_hours == 5.0
    assert report.implementation_order == ["REQ-1"]
