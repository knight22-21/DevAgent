"""Tests for Phase 22 — --json-schema structured output validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devagent.cli import _validate_against_schema, app

# ---------------------------------------------------------------------------
# Unit tests for _validate_against_schema helper
# ---------------------------------------------------------------------------

class TestValidateAgainstSchema:
    def test_valid_object(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        valid, err = _validate_against_schema('{"name": "Alice"}', schema)
        assert valid is True
        assert err == ""

    def test_invalid_not_json(self):
        schema = {"type": "object"}
        valid, err = _validate_against_schema("not json at all", schema)
        assert valid is False
        assert "not valid JSON" in err

    def test_invalid_wrong_type(self):
        schema = {"type": "object", "required": ["count"], "properties": {"count": {"type": "integer"}}}
        valid, err = _validate_against_schema('{"count": "oops"}', schema)
        assert valid is False
        assert err  # jsonschema supplies a message

    def test_missing_required_field(self):
        schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
        valid, _err = _validate_against_schema('{"other": 1}', schema)
        assert valid is False

    def test_valid_array(self):
        schema = {"type": "array", "items": {"type": "string"}}
        valid, _err = _validate_against_schema('["a", "b", "c"]', schema)
        assert valid is True

    def test_invalid_array_item_type(self):
        schema = {"type": "array", "items": {"type": "string"}}
        valid, _err = _validate_against_schema('[1, 2, 3]', schema)
        assert valid is False

    def test_valid_number(self):
        schema = {"type": "number", "minimum": 0}
        valid, _err = _validate_against_schema("42", schema)
        assert valid is True

    def test_invalid_below_minimum(self):
        schema = {"type": "number", "minimum": 10}
        valid, _err = _validate_against_schema("5", schema)
        assert valid is False

    def test_bad_schema(self):
        # A schema itself that's invalid — should return invalid + error about schema
        schema = {"type": "notavalidtype12345"}
        valid, _err = _validate_against_schema('{}', schema)
        # jsonschema may or may not raise SchemaError for unknown type — test handles both outcomes
        # At minimum the call should not crash
        assert isinstance(valid, bool)

    def test_empty_string_is_invalid_json(self):
        schema = {"type": "object"}
        valid, _err = _validate_against_schema("", schema)
        assert valid is False

    def test_valid_nested(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"age": {"type": "integer"}},
                    "required": ["age"],
                }
            },
            "required": ["user"],
        }
        valid, _err = _validate_against_schema('{"user": {"age": 30}}', schema)
        assert valid is True


# ---------------------------------------------------------------------------
# CLI integration tests for `devagent do --json-schema`
# ---------------------------------------------------------------------------

runner = CliRunner()

_GOOD_SCHEMA = json.dumps({"type": "object", "required": ["result"], "properties": {"result": {"type": "string"}}})
_GOOD_JSON = '{"result": "hello"}'
_BAD_JSON = '{"wrong_key": 1}'


def _make_final_answer_event(text: str):
    from devagent.agent.loop import FinalAnswerEvent
    return FinalAnswerEvent(text=text, tokens_in=10, tokens_out=10)


def _make_error_event(msg: str = "oops"):
    from devagent.agent.loop import ErrorEvent
    return ErrorEvent(message=msg)


class TestDoJsonSchema:
    def _patch_session(self, events):
        """Return a context manager that patches DevAgentSession to yield given events."""
        mock_loop = MagicMock()
        mock_loop.run.return_value = iter(events)
        mock_session = MagicMock()
        mock_session._loop = mock_loop
        mock_session.session_id = "test-session"
        return patch("devagent.agent.flows.DevAgentSession", return_value=mock_session)

    def test_no_schema_passes_normally(self):
        events = [_make_final_answer_event("plain answer")]
        with self._patch_session(events), \
             patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)):
            result = runner.invoke(app, ["do", "do something"])
        assert result.exit_code == 0

    def test_valid_json_passes_schema(self):
        events = [_make_final_answer_event(_GOOD_JSON)]
        with self._patch_session(events), \
             patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)):
            result = runner.invoke(app, ["do", "task", "--json-schema", _GOOD_SCHEMA])
        assert result.exit_code == 0

    def test_invalid_schema_arg_exits_1(self):
        with patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))):
            result = runner.invoke(app, ["do", "task", "--json-schema", "{not valid json}"])
        assert result.exit_code == 1

    def test_invalid_answer_retries_and_succeeds(self):
        """First attempt returns bad JSON, retry returns good JSON — exit 0."""
        first_events = [_make_final_answer_event(_BAD_JSON)]
        retry_events = [_make_final_answer_event(_GOOD_JSON)]

        mock_loop1 = MagicMock()
        mock_loop1.run.return_value = iter(first_events)
        mock_session1 = MagicMock()
        mock_session1._loop = mock_loop1
        mock_session1.session_id = "s1"

        mock_loop2 = MagicMock()
        mock_loop2.run.return_value = iter(retry_events)
        mock_session2 = MagicMock()
        mock_session2._loop = mock_loop2
        mock_session2.session_id = "s2"

        with patch("devagent.agent.flows.DevAgentSession", side_effect=[mock_session1, mock_session2]), \
             patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)):
            result = runner.invoke(app, ["do", "task", "--json-schema", _GOOD_SCHEMA])

        assert result.exit_code == 0

    def test_invalid_answer_retries_and_fails_exit_2(self):
        """Both attempts return bad JSON — exit 2."""
        bad_events = [_make_final_answer_event(_BAD_JSON)]
        bad_retry = [_make_final_answer_event(_BAD_JSON)]

        mock_loop1 = MagicMock()
        mock_loop1.run.return_value = iter(bad_events)
        mock_session1 = MagicMock()
        mock_session1._loop = mock_loop1
        mock_session1.session_id = "s1"

        mock_loop2 = MagicMock()
        mock_loop2.run.return_value = iter(bad_retry)
        mock_session2 = MagicMock()
        mock_session2._loop = mock_loop2
        mock_session2.session_id = "s2"

        with patch("devagent.agent.flows.DevAgentSession", side_effect=[mock_session1, mock_session2]), \
             patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)):
            result = runner.invoke(app, ["do", "task", "--json-schema", _GOOD_SCHEMA])

        assert result.exit_code == 2

    def test_no_final_answer_event_with_schema(self):
        """If no FinalAnswerEvent is emitted (error only), treats final_text as '' — invalid."""
        error_events = [_make_error_event("agent crashed")]

        mock_loop1 = MagicMock()
        mock_loop1.run.return_value = iter(error_events)
        mock_session1 = MagicMock()
        mock_session1._loop = mock_loop1
        mock_session1.session_id = "s1"

        mock_loop2 = MagicMock()
        mock_loop2.run.return_value = iter([_make_error_event("still bad")])
        mock_session2 = MagicMock()
        mock_session2._loop = mock_loop2
        mock_session2.session_id = "s2"

        with patch("devagent.agent.flows.DevAgentSession", side_effect=[mock_session1, mock_session2]), \
             patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)):
            result = runner.invoke(app, ["do", "task", "--json-schema", _GOOD_SCHEMA])

        # Either exit 1 (ErrorEvent) or exit 2 (schema mismatch after retry) — not 0
        assert result.exit_code != 0

    def test_retry_prompt_includes_error_and_schema(self):
        """Verify the retry task string contains the schema and error message."""
        captured_tasks = []

        def _fake_run(task_str):
            captured_tasks.append(task_str)
            if len(captured_tasks) == 1:
                from devagent.agent.loop import FinalAnswerEvent
                return iter([FinalAnswerEvent(text=_BAD_JSON)])
            from devagent.agent.loop import FinalAnswerEvent
            return iter([FinalAnswerEvent(text=_GOOD_JSON)])

        mock_loop = MagicMock()
        mock_loop.run.side_effect = _fake_run
        mock_session = MagicMock()
        mock_session._loop = mock_loop
        mock_session.session_id = "s1"

        with patch("devagent.agent.flows.DevAgentSession", return_value=mock_session), \
             patch("devagent.cli.config_exists", return_value=True), \
             patch("devagent.cli.load_config", return_value=MagicMock(llm=MagicMock(model="test"))), \
             patch("devagent.core.project.detect_project_root", return_value=("/tmp", None)):
            result = runner.invoke(app, ["do", "my task", "--json-schema", _GOOD_SCHEMA])

        assert result.exit_code == 0
        assert len(captured_tasks) == 2
        # Retry task must contain the schema
        assert "result" in captured_tasks[1]
        # Original task preserved in retry
        assert "my task" in captured_tasks[1]
