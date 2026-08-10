import pytest
from devagent.core.models import GapReport, Requirement, RequirementAnalysis, RequirementType, RequirementStatus, EffortEstimate
from devagent.chat.context import build_system_prompt, estimate_prompt_tokens

def test_estimate_prompt_tokens():
    text = "a" * 40
    assert estimate_prompt_tokens(text) == 10

def test_build_system_prompt():
    req = Requirement(
        id="REQ-1",
        description="A test requirement",
        requirement_type=RequirementType.FEATURE,
        priority="high",
        raw_text="A test requirement"
    )
    
    analysis = RequirementAnalysis(
        requirement=req,
        status=RequirementStatus.MISSING,
        matched_files=[],
        matched_functions=[],
        classification_reason="Does not exist yet"
    )
    
    report = GapReport(
        spec_source="Test Spec",
        reuse=[],
        extend=[],
        conflicts=[],
        net_new=[analysis],
        edge_cases=[],
        data_models=[],
        api_changes=[],
        effort_estimate=EffortEstimate(
            conflict_resolution_hours=0,
            extension_hours=0,
            net_new_hours=4,
            testing_hours=2,
            total_days=1.0,
            confidence="high",
            notes="Simple"
        ),
        implementation_order=["Do REQ-1"]
    )
    
    prompt = build_system_prompt(report, "TestProject")
    
    assert "PROJECT: TestProject" in prompt
    assert "SPEC SOURCE: Test Spec" in prompt
    assert "[REQ-1] A test requirement" in prompt
    assert "Type: feature" in prompt
    assert "Status: MISSING" in prompt
    assert "1. Do REQ-1" in prompt
    assert "Net new work: 4.0h" in prompt
