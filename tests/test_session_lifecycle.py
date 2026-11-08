"""Session status follows execution rather than unrelated database writes."""

import os
import sqlite3
import subprocess
import sys
import sysconfig
import threading
import time
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from devagent.agent.flows import DevAgentSession
from devagent.agent.loop import ErrorEvent, FinalAnswerEvent
from devagent.agent.orchestrator import OrchestratorSession
from devagent.agent.task_graph import TaskNode
from devagent.agent.worker import Worker
from devagent.server.fastapi_app import _derive_status, create_app
from devagent.session import store
from devagent.session.manager import SessionManager


def test_status_survives_age_and_unrelated_updates(tmp_path):
    mgr = SessionManager(tmp_path / "sessions.db")
    sid = mgr.new(metadata={"project_setting": "kept"})
    mgr.set_status(sid, "running")
    with sqlite3.connect(mgr.db_path) as conn:
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (time.time() - 300, sid))
    assert _derive_status(mgr.get(sid)) == "running"
    mgr.set_status(sid, "completed")
    mgr.set_title(sid, "new title")
    session = mgr.get(sid)
    assert _derive_status(session) == "completed"
    assert session["metadata"] == {"project_setting": "kept"}


def test_status_in_public_endpoints(tmp_path, monkeypatch):
    db = tmp_path / "sessions.db"
    mgr = SessionManager(db)
    sid = mgr.new()
    original_conn = store._conn
    monkeypatch.setattr(store, "_conn", lambda db_path=None: original_conn(db_path or db))
    client = TestClient(create_app(config=None, project_root="."))
    mgr.set_status(sid, "running")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (time.time() - 300, sid))
    assert client.get(f"/api/v1/sessions/{sid}").json()["status"] == "running"
    assert client.get("/api/v1/sessions", params={"status": "running"}).json()["total"] == 1
    assert client.get("/api/v1/status").json()["active_sessions"] == 1
    mgr.set_status(sid, "completed")
    mgr.set_title(sid, "changed after exit")
    assert client.get(f"/api/v1/sessions/{sid}").json()["status"] == "completed"
    assert client.get("/api/v1/sessions", params={"status": "running"}).json()["total"] == 0
    assert client.get("/api/v1/status").json()["active_sessions"] == 0


def test_metadata_status_remains_compatible(tmp_path):
    db = tmp_path / "sessions.db"
    mgr = SessionManager(db)
    sid = mgr.new(metadata={"status": "failed"})
    assert mgr.get(sid)["status"] == "failed"
    store.update_session(sid, metadata={"status": "running", "other": 1}, db_path=db)
    assert mgr.get(sid)["status"] == "running"
    store.update_session(sid, metadata={"other": 2}, db_path=db)
    assert mgr.get(sid)["status"] == "running"


def test_migration_preserves_legacy_metadata_status(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE sessions (
            id TEXT PRIMARY KEY, project TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL,
            updated_at REAL NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')""")
        conn.execute("INSERT INTO sessions (id, created_at, updated_at, metadata) VALUES (?, ?, ?, ?)",
                     ("old", 0, 0, '{"status":"failed","other":42}'))
        conn.execute("INSERT INTO sessions (id, created_at, updated_at, metadata) VALUES (?, ?, ?, ?)",
                     ("null", 0, 0, '{"status":null}'))
    store.init_schema(db)
    store.init_schema(db)
    session = store.get_session("old", db)
    assert _derive_status(session) == "failed"
    assert session["metadata"]["other"] == 42
    assert store.get_session("null", db)["status"] == "completed"


def make_session(tmp_path, events):
    mgr = SessionManager(tmp_path / "sessions.db")
    session = DevAgentSession.__new__(DevAgentSession)
    session._mgr = mgr
    session.session_id = mgr.new()
    session._interactive_running = False
    session._plan_mode = False

    class Loop:
        def run(self, message):
            assert mgr.get(session.session_id)["status"] == "running"
            yield from events

    session._loop = Loop()
    return session


@pytest.mark.parametrize(("events", "expected"), [
    ([FinalAnswerEvent(text="ok")], "completed"),
    ([ErrorEvent("provider failed")], "failed"),
])
def test_single_message_tracks_success_and_error(tmp_path, events, expected):
    session = make_session(tmp_path, events)
    session.run_message("hello", quiet=True)
    assert session._mgr.get(session.session_id)["status"] == expected


def test_single_message_exception_marks_failed(tmp_path):
    session = make_session(tmp_path, [])

    def fail(_message):
        raise RuntimeError("failure")

    session._loop = SimpleNamespace(run=fail)
    with pytest.raises(RuntimeError, match="failure"):
        session.run_message("hello", quiet=True)
    assert session._mgr.get(session.session_id)["status"] == "failed"


def test_event_stream_tracks_failure_and_closure(tmp_path):
    session = make_session(tmp_path, [ErrorEvent("provider failed")])
    assert len(list(session.run_events("hello"))) == 1
    assert session._mgr.get(session.session_id)["status"] == "failed"
    session._loop.run = lambda message: iter([FinalAnswerEvent(text="ok")])
    stream = session.run_events("hello")
    next(stream)
    assert session._mgr.get(session.session_id)["status"] == "running"
    stream.close()
    assert session._mgr.get(session.session_id)["status"] == "failed"


def test_interactive_session_stays_running_between_messages(tmp_path):
    session = make_session(tmp_path, [FinalAnswerEvent(text="ok")])

    def repl(*, first_message):
        session.run_message("hello", quiet=True)
        assert session._mgr.get(session.session_id)["status"] == "running"

    session._interactive_repl = repl
    session.interactive_repl()
    assert session._mgr.get(session.session_id)["status"] == "completed"


def test_interactive_failure_and_resume(tmp_path):
    session = make_session(tmp_path, [])

    def fail(*, first_message):
        raise RuntimeError("interrupted")

    session._interactive_repl = fail
    with pytest.raises(RuntimeError, match="interrupted"):
        session.interactive_repl()
    assert session._mgr.get(session.session_id)["status"] == "failed"
    session._interactive_repl = lambda *, first_message: None
    session.interactive_repl()
    assert session._mgr.get(session.session_id)["status"] == "completed"


def test_clear_moves_interactive_run_to_new_session(tmp_path, monkeypatch):
    session = make_session(tmp_path, [])
    old_id = session.session_id
    session._cfg = SimpleNamespace(llm=SimpleNamespace(model="test", provider="test"))
    session._project_root = tmp_path
    session._console = SimpleNamespace(print=lambda *args, **kwargs: None)
    session._undo_stack = []
    session._print_exit = lambda: None

    class Prompt:
        calls = 0

        def prompt(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return "/clear"
            assert session._mgr.get(old_id)["status"] == "completed"
            assert session._mgr.get(session.session_id)["status"] == "running"
            return "/exit"

    monkeypatch.setattr("prompt_toolkit.PromptSession", lambda **kwargs: Prompt())
    session.interactive_repl()
    assert session.session_id != old_id
    assert session._mgr.get(session.session_id)["status"] == "completed"


def test_worker_initialization_failure_marks_session_failed(tmp_path, monkeypatch):
    mgr = SessionManager(tmp_path / "sessions.db")
    monkeypatch.setattr("devagent.session.manager.SessionManager", lambda: mgr)

    def fail_registry(**kwargs):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr("devagent.tools.registry.build_registry", fail_registry)
    cfg = SimpleNamespace(llm=SimpleNamespace(model="test", provider="test"),
                          github=SimpleNamespace(token=""))
    node = TaskNode(id="one", description="task")
    result = Worker(task=node, cfg=cfg, project_root=str(tmp_path), coordinator_session_id="").run()
    assert not result.success
    assert result.error == "registry unavailable"
    assert mgr.get(node.assigned_session)["status"] == "failed"


def test_orchestrator_marks_failure_and_closure(tmp_path):
    mgr = SessionManager(tmp_path / "sessions.db")
    session = OrchestratorSession.__new__(OrchestratorSession)
    session._mgr = mgr
    session._session_id = mgr.new()
    session._run = lambda task: iter([ErrorEvent("failed")])
    assert len(list(session.run("task"))) == 1
    assert mgr.get(session.session_id)["status"] == "failed"

    session._run = lambda task: iter([FinalAnswerEvent(text="ok")])
    assert len(list(session.run("task"))) == 1
    assert mgr.get(session.session_id)["status"] == "completed"

    stream = session.run("task")
    next(stream)
    assert mgr.get(session.session_id)["status"] == "running"
    stream.close()
    assert mgr.get(session.session_id)["status"] == "failed"


def test_overlapping_messages_keep_session_running_until_both_finish(tmp_path):
    session = make_session(tmp_path, [])
    started = threading.Event()
    release = threading.Event()

    def slow_message(message, quiet=False):
        started.set()
        assert release.wait(5)
        return "done"

    session._run_message = slow_message
    thread = threading.Thread(target=session.run_message, args=("slow",))
    thread.start()
    try:
        assert started.wait(5)
        other = make_session(tmp_path, [])
        other.session_id = session.session_id
        other._run_message = lambda message, quiet=False: "done"
        other.run_message("fast", quiet=True)
        assert session._mgr.get(session.session_id)["status"] == "running"
    finally:
        release.set()
        thread.join(timeout=5)


def test_overlapping_messages_keep_error_outcomes_separate(tmp_path):
    session = make_session(tmp_path, [])
    failed = threading.Event()
    release = threading.Event()

    def run(message):
        if message == "fail":
            yield ErrorEvent("provider failed")
            failed.set()
            assert release.wait(10)
        yield FinalAnswerEvent(text="done")

    session._loop.run = run
    thread = threading.Thread(target=session.run_message, args=("fail",), kwargs={"quiet": True})
    thread.start()
    try:
        assert failed.wait(10)
        session.run_message("success", quiet=True)
        assert session._mgr.get(session.session_id)["status"] == "running"
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert session._mgr.get(session.session_id)["status"] == "failed"


def test_process_exit_recovers_stale_run(tmp_path):
    db = tmp_path / "sessions.db"
    mgr = SessionManager(db)
    sid = mgr.new()
    code = (
        "import sys,time; from pathlib import Path; "
        "from devagent.session.manager import SessionManager; "
        "m=SessionManager(Path(sys.argv[1])); m.begin_run(sys.argv[2]); "
        "print('started', flush=True); time.sleep(60)"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [sysconfig.get_path("purelib"), env.get("PYTHONPATH")]))
    process = subprocess.Popen(
        [sys._base_executable or sys.executable, "-c", code, str(db), sid],
        stdout=subprocess.PIPE, text=True, env=env,
    )
    try:
        assert process.stdout.readline().strip() == "started"
        assert mgr.get(sid)["status"] == "running"
    finally:
        process.kill()
        process.wait(timeout=10)
        process.stdout.close()
    assert mgr.get(sid)["status"] == "failed"


def test_stale_run_does_not_override_live_run(tmp_path):
    mgr = SessionManager(tmp_path / "sessions.db")
    sid = mgr.new()
    run_id = mgr.begin_run(sid)
    with sqlite3.connect(mgr.db_path) as conn:
        conn.execute(
            "INSERT INTO session_runs (id, session_id, pid, process_started) VALUES (?, ?, ?, ?)",
            ("stale", sid, os.getpid(), 0),
        )
    mgr.close(sid)
    store.update_session(sid, metadata={"status": "completed"}, db_path=mgr.db_path)
    assert mgr.get(sid)["status"] == "running"
    mgr.finish_run(sid, run_id, "completed")
    assert mgr.get(sid)["status"] == "completed"


def test_finish_recovers_stale_run_before_recording_later_success(tmp_path):
    mgr = SessionManager(tmp_path / "sessions.db")
    sid = mgr.new()
    run_id = mgr.begin_run(sid)
    with sqlite3.connect(mgr.db_path) as conn:
        conn.execute(
            "INSERT INTO session_runs (id, session_id, pid, process_started) VALUES (?, ?, ?, ?)",
            ("stale", sid, os.getpid(), 0),
        )
    mgr.finish_run(sid, run_id, "completed")
    assert mgr.get(sid)["status"] == "completed"
