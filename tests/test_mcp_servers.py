import json
import pytest
from specsync.core.models import Requirement, RequirementType

# We need to monkeypatch the LLM call inside the tool
from specsync.mcp.servers.spec_analysis.server import parse_spec_to_requirements
from specsync.mcp.servers.code_search.server import semantic_search

@pytest.mark.asyncio
async def test_parse_spec_to_requirements_mcp(monkeypatch):
    # Mock the LLM response directly
    class MockResponse:
        content = json.dumps([{
            "id": "REQ-1",
            "description": "Add a new endpoint",
            "requirement_type": "api_change",
            "priority": "high",
            "raw_text": "The system must have an endpoint."
        }])

    class MockLLM:
        async def ainvoke(self, *args, **kwargs):
            return MockResponse()

        def invoke(self, *args, **kwargs):
            return MockResponse()

    # Patch _get_llm which is what the server actually calls
    monkeypatch.setattr("specsync.mcp.servers.spec_analysis.server._get_llm", lambda: MockLLM())

    # We also need to patch load_config because the server loads config internally
    class MockConfig:
        class LLM:
            provider = "ollama"
        llm = LLM()
    monkeypatch.setattr("specsync.mcp.servers.spec_analysis.server.load_config", lambda: MockConfig())

    result_json = await parse_spec_to_requirements("The system must have an endpoint.")

    result = json.loads(result_json)
    assert len(result) == 1
    assert result[0]["id"] == "REQ-1"
    assert result[0]["requirement_type"] == "api_change"


@pytest.mark.asyncio
async def test_code_search_semantic_search_mcp(monkeypatch):
    # Mock the Chroma collection and embedding
    class MockCollection:
        def query(self, *args, **kwargs):
            return {
                "ids": [["test_py_0"]],
                "distances": [[0.5]],
                "documents": [["def test(): pass"]],
                "metadatas": [[{
                    "file_path": "test.py",
                    "chunk_type": "function",
                    "name": "test",
                    "start_line": 1,
                    "end_line": 2
                }]]
            }
            
    class MockEmbedder:
        def encode(self, texts):
            class Arr:
                def tolist(self): return [0.1] * 384
            return Arr()
            
    monkeypatch.setattr("specsync.mcp.servers.code_search.server._get_chroma_collection", lambda p: MockCollection())
    monkeypatch.setattr("specsync.mcp.servers.code_search.server._get_embedding_model", lambda: MockEmbedder())
    
    result_json = await semantic_search("find test function", "/fake/path")
    
    result = json.loads(result_json)
    assert len(result) == 1
    assert result[0]["file_path"] == "test.py"
    assert result[0]["name"] == "test"
    # similarity is 1.0 - 0.5/2 = 0.75
    assert result[0]["similarity_score"] == 0.75