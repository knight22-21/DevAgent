"""Gemini tool calling: definitions must reach the request, FunctionCall parts must come back.

Offline by construction: the SDK's own request builder runs for real
(``GenerativeModel.generate_content`` -> ``_prepare_request``), and only the transport
client (``model._client``) is a fake. So ``request.tools`` is exactly what the SDK would
put on the wire, and the canned response exercises the real ``GenerateContentResponse``
wrapper. No network, no API key.

Regression tests for the Gemini path in ``devagent.core.llm``: the provider accepted a
``tools`` argument -- and dropped it. The model therefore received a plain text prompt with
no tool definitions, answered in prose, and every tool-using task on that provider ended
early with an incomplete result.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest

warnings.filterwarnings("ignore")  # google-generativeai emits a deprecation FutureWarning

import google.generativeai as genai
from google.generativeai import generative_models as genai_models
from google.generativeai import protos

from devagent.core.config import LLMConfig
from devagent.core.llm import (
    AgentMessage,
    LLMClient,
    Message,
    ToolDef,
    _to_gemini_schema,
    _to_gemini_tools,
)
from devagent.tools.registry import build_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fake transport — the SDK builds the request, we only stand in for the network
# ---------------------------------------------------------------------------


class _FakeTransport:
    """Captures the request the SDK built and returns a canned response."""

    def __init__(self, response: protos.GenerateContentResponse) -> None:
        self.request: Any = None
        self.response = response

    def generate_content(self, request: Any, **kwargs: Any) -> protos.GenerateContentResponse:
        self.request = request
        return self.response

    def stream_generate_content(self, request: Any, **kwargs: Any):
        self.request = request
        yield self.response


def _text_response(text: str = "ok") -> protos.GenerateContentResponse:
    return protos.GenerateContentResponse(
        candidates=[
            protos.Candidate(
                content=protos.Content(parts=[protos.Part(text=text)], role="model")
            )
        ],
        usage_metadata=protos.GenerateContentResponse.UsageMetadata(
            prompt_token_count=11, candidates_token_count=7
        ),
    )


def _function_call_response(*calls: tuple[str, dict]) -> protos.GenerateContentResponse:
    return protos.GenerateContentResponse(
        candidates=[
            protos.Candidate(
                content=protos.Content(
                    parts=[
                        protos.Part(
                            function_call=protos.FunctionCall(name=name, args=args)
                        )
                        for name, args in calls
                    ],
                    role="model",
                )
            )
        ]
    )


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch):
    """A gemini-configured client plus a hook to swap in a canned response."""

    def _build(response: protos.GenerateContentResponse) -> tuple[LLMClient, _FakeTransport]:
        transport = _FakeTransport(response)
        real_model = genai_models.GenerativeModel("gemini-1.5-flash")
        real_model._client = transport
        # the provider does `import google.generativeai as genai; genai.GenerativeModel(...)`
        monkeypatch.setattr(genai, "GenerativeModel", lambda *a, **k: real_model)
        client = LLMClient(
            LLMConfig(provider="gemini", model="gemini-1.5-flash", api_key="test-key")
        )
        return client, transport

    return _build


def _tool_defs() -> list[ToolDef]:
    return [
        ToolDef(
            name="read_file",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "file path"},
                    "start_line": {"type": "integer", "default": 1},
                },
                "required": ["path"],
            },
        ),
        ToolDef(
            name="grep",
            description="Search",
            parameters={
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# The definitions reach the request
# ---------------------------------------------------------------------------


class TestToolDefinitionsReachTheRequest:
    def test_names_and_schemas_are_on_the_wire(self, gemini) -> None:
        client, transport = gemini(_text_response())

        client.complete_with_tools(
            [AgentMessage(role="user", content="read main.py")], _tool_defs()
        )

        declarations = transport.request.tools[0].function_declarations
        assert [d.name for d in declarations] == ["read_file", "grep"]

        read_file = declarations[0]
        assert read_file.description == "Read a file"
        # The SDK renamed+uppercased our JSON-Schema `type` -> the proto enum
        assert read_file.parameters.type_ == protos.Type.OBJECT
        assert read_file.parameters.properties["path"].type_ == protos.Type.STRING
        assert list(read_file.parameters.required) == ["path"]

    def test_no_tools_means_no_tools_on_the_wire(self, gemini) -> None:
        client, transport = gemini(_text_response())

        client.complete([Message(role="user", content="hi")])

        assert list(transport.request.tools) == []

    def test_empty_tool_list_adds_no_tools(self, gemini) -> None:
        client, transport = gemini(_text_response())

        client.complete_with_tools([AgentMessage(role="user", content="hi")], [])

        assert list(transport.request.tools) == []

    def test_every_shipped_tool_schema_marshals(self, gemini) -> None:
        """The registry's own schemas are the ones that must survive the conversion.

        Ten of them carry a JSON-Schema ``default``, which Gemini's Schema proto has no
        field for -- passing a tool schema through unchanged raises
        ``ValueError: Unknown field for Schema: default``.
        """
        client, transport = gemini(_text_response())
        defs = build_registry(str(REPO_ROOT)).get_definitions()
        assert len(defs) > 1

        client.complete_with_tools([AgentMessage(role="user", content="hi")], defs)

        names = [d.name for d in transport.request.tools[0].function_declarations]
        assert names == [d.name for d in defs]


# ---------------------------------------------------------------------------
# The schema conversion itself
# ---------------------------------------------------------------------------


class TestSchemaConversion:
    def test_unsupported_keywords_are_dropped(self) -> None:
        schema = {
            "type": "object",
            "title": "Args",
            "additionalProperties": False,
            "$defs": {"X": {"type": "string"}},
            "properties": {
                "path": {"type": "string", "default": "x.py", "title": "Path"},
                "tags": {"type": "array", "items": {"type": "string", "title": "Tag"}},
            },
            "required": ["path"],
            "minItems": 1,
            "maxItems": 5,
            "minimum": 0,
        }

        out = _to_gemini_schema(schema)

        assert out == {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["path"],
            "min_items": 1,
            "max_items": 5,
        }

    def test_converted_schema_is_accepted_by_the_sdk(self, gemini) -> None:
        client, transport = gemini(_text_response())
        tools = [
            ToolDef(
                name="t",
                description="d",
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"p": {"type": "string", "default": "z"}},
                },
            )
        ]

        client.complete_with_tools([AgentMessage(role="user", content="hi")], tools)

        params = transport.request.tools[0].function_declarations[0].parameters
        assert params.type_ == protos.Type.OBJECT
        assert params.properties["p"].type_ == protos.Type.STRING

    def test_description_and_enum_survive(self) -> None:
        out = _to_gemini_schema(
            {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["a", "b"], "description": "pick one"}
                },
            }
        )
        assert out["properties"]["mode"]["enum"] == ["a", "b"]
        assert out["properties"]["mode"]["description"] == "pick one"

    def test_to_gemini_tools_shape(self) -> None:
        payload = _to_gemini_tools(_tool_defs())
        assert len(payload) == 1  # one Tool carrying every declaration
        assert [d["name"] for d in payload[0]["function_declarations"]] == ["read_file", "grep"]


# ---------------------------------------------------------------------------
# The reply comes back as tool calls
# ---------------------------------------------------------------------------


class TestFunctionCallResponses:
    def test_function_call_becomes_a_tool_call(self, gemini) -> None:
        client, _ = gemini(_function_call_response(("read_file", {"path": "main.py"})))

        resp = client.complete_with_tools(
            [AgentMessage(role="user", content="read main.py")], _tool_defs()
        )

        assert resp.has_tool_calls
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"
        assert resp.tool_calls[0].args == {"path": "main.py"}
        assert resp.tool_calls[0].id  # Gemini sends no id; one is minted locally
        assert resp.content == ""  # no text part -- must not go through resp.text
        assert resp.provider == "gemini"

    def test_several_function_calls_keep_distinct_ids(self, gemini) -> None:
        client, _ = gemini(
            _function_call_response(("read_file", {"path": "a.py"}), ("grep", {"pattern": "x"}))
        )

        resp = client.complete_with_tools(
            [AgentMessage(role="user", content="go")], _tool_defs()
        )

        assert [c.name for c in resp.tool_calls] == ["read_file", "grep"]
        assert [c.args for c in resp.tool_calls] == [{"path": "a.py"}, {"pattern": "x"}]
        assert len({c.id for c in resp.tool_calls}) == 2

    def test_text_only_reply_still_works(self, gemini) -> None:
        client, _ = gemini(_text_response("the answer is 42"))

        resp = client.complete_with_tools(
            [AgentMessage(role="user", content="hi")], _tool_defs()
        )

        assert resp.content == "the answer is 42"
        assert resp.tool_calls == []
        assert resp.input_tokens == 11
        assert resp.output_tokens == 7

    def test_text_and_function_call_together(self, gemini) -> None:
        response = protos.GenerateContentResponse(
            candidates=[
                protos.Candidate(
                    content=protos.Content(
                        parts=[
                            protos.Part(text="let me look"),
                            protos.Part(
                                function_call=protos.FunctionCall(
                                    name="read_file", args={"path": "main.py"}
                                )
                            ),
                        ],
                        role="model",
                    )
                )
            ]
        )
        client, _ = gemini(response)

        resp = client.complete_with_tools(
            [AgentMessage(role="user", content="hi")], _tool_defs()
        )

        assert resp.content == "let me look"
        assert [c.name for c in resp.tool_calls] == ["read_file"]

    def test_response_without_candidates_does_not_raise(self, gemini) -> None:
        client, _ = gemini(protos.GenerateContentResponse())

        resp = client.complete_with_tools(
            [AgentMessage(role="user", content="hi")], _tool_defs()
        )

        assert resp.content == ""
        assert resp.tool_calls == []
