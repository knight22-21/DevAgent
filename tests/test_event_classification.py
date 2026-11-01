"""`_classify_event` must read the roles the session store actually writes."""

from __future__ import annotations

from devagent.server.fastapi_app import _classify_event


def test_tool_result_event_is_classified_as_a_tool_result() -> None:
    # SessionManager.record_tool_result() stores role="tool_result".
    assert _classify_event({"role": "tool_result", "tool_name": "read_file"}) == "tool_result"


def test_legacy_tool_role_still_classifies_as_a_tool_result() -> None:
    assert _classify_event({"role": "tool"}) == "tool_result"


def test_other_roles_keep_their_classification() -> None:
    assert _classify_event({"role": "user"}) == "user_message"
    assert _classify_event({"role": "assistant", "tool_calls": [{"id": "1"}]}) == "tool_call"
    assert _classify_event({"role": "assistant"}) == "thinking"
    assert _classify_event({"role": "system"}) == "status"
    assert _classify_event({}) == "status"
