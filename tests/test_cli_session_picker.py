from __future__ import annotations

from unittest.mock import Mock

from devagent import cli


def test_pick_session_uses_arrow_picker(monkeypatch) -> None:
    sessions = [{"id": "session-one", "title": "First session"}]
    dialog = Mock()
    dialog.run.return_value = "session-one"
    picker = Mock(return_value=dialog)
    monkeypatch.setattr("prompt_toolkit.shortcuts.radiolist_dialog", picker)

    assert cli._pick_session(sessions) == "session-one"
    picker.assert_called_once()
    assert picker.call_args.kwargs["values"] == [
        ("session-one", "First session"),
        ("", "Start new session"),
    ]


def test_pick_session_numeric_fallback(monkeypatch) -> None:
    sessions = [
        {"id": "session-one", "title": "First session"},
        {"id": "session-two", "title": "Second session"},
    ]
    monkeypatch.setattr(
        "prompt_toolkit.shortcuts.radiolist_dialog",
        Mock(side_effect=ImportError),
    )
    monkeypatch.setattr(cli.console, "input", lambda _: "2")

    assert cli._pick_session(sessions) == "session-two"
