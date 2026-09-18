"""Tests for the FastAPI REST + WebSocket API server (devagent/server/fastapi_app.py).

These tests use starlette's TestClient which runs the ASGI app in-process —
no real network socket needed, no uvicorn process started.
"""

from __future__ import annotations

import time

import pytest
from starlette.testclient import TestClient

from devagent.server.fastapi_app import create_app
from devagent.session import store as session_store

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Return a TestClient configured with no LLM config."""
    app = create_app(config=None, project_root=".")
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def client_with_config():
    """Return a TestClient configured with a real LLM config object."""
    from devagent.core.config import DevAgentConfig, LLMConfig
    cfg = DevAgentConfig(llm=LLMConfig(provider="ollama", model="qwen2.5-coder:7b"))
    app = create_app(config=cfg, project_root=".")
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def session_id(tmp_path):
    """Create a temporary session in the real DB and clean it up after."""
    sid = f"test-api-{int(time.time() * 1000)}"
    session_store.init_schema()
    session_store.create_session(
        sid,
        project="/test/project",
        model="qwen2.5-coder:7b",
        provider="ollama",
        title="API test session",
    )
    yield sid
    try:
        session_store.delete_session(sid)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Health + status
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_v1_status_no_config(client):
    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "version" in body
    assert "uptime_seconds" in body
    assert "total_sessions" in body
    assert "active_sessions" in body
    assert body["llm"]["provider"] is None  # no config


def test_v1_status_with_config(client_with_config):
    resp = client_with_config.get("/api/v1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm"]["provider"] == "ollama"
    assert body["llm"]["model"] == "qwen2.5-coder:7b"
    assert body["llm"]["offline_capable"] is True


def test_legacy_status_no_config_returns_503(client):
    """The /api/status legacy endpoint preserves the old 503 behaviour when unconfigured."""
    resp = client.get("/api/status")
    assert resp.status_code == 503
    assert "error" in resp.json()


def test_legacy_status_with_config(client_with_config):
    resp = client_with_config.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm"]["provider"] == "ollama"
    assert body["llm"]["offline_capable"] is True


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

def test_cors_options(client):
    # CORS middleware only adds headers when Origin is present (browser preflight behaviour)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


def test_cors_get(client):
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# Session list
# ---------------------------------------------------------------------------

def test_v1_sessions_returns_list(client):
    resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body
    assert isinstance(body["sessions"], list)
    assert "total" in body


def test_v1_sessions_pagination(client):
    resp = client.get("/api/v1/sessions?limit=5&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) <= 5


def test_legacy_sessions(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert "sessions" in resp.json()


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------

def test_v1_session_not_found(client):
    resp = client.get("/api/v1/sessions/nonexistent-session-xyz-000")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_v1_session_detail(client, session_id):
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == session_id
    assert body["model"] == "qwen2.5-coder:7b"
    assert body["provider"] == "ollama"
    assert "status" in body
    assert body["status"] in ("running", "completed", "error", "paused")
    assert "token_input" in body
    assert "token_output" in body
    assert "cost_usd" in body
    assert "is_orchestrate" in body
    assert body["is_orchestrate"] is False


def test_v1_session_appears_in_list(client, session_id):
    resp = client.get("/api/v1/sessions")
    ids = [s["id"] for s in resp.json()["sessions"]]
    assert session_id in ids


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------

def test_v1_events_empty(client, session_id):
    resp = client.get(f"/api/v1/sessions/{session_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []
    assert body["has_more"] is False


def test_v1_events_not_found(client):
    resp = client.get("/api/v1/sessions/nonexistent-xyz/events")
    assert resp.status_code == 404


def test_v1_events_with_data(client, session_id):
    # Append some events to the session
    session_store.append_event(session_id, role="user", content="write a hello world script")
    session_store.append_event(session_id, role="assistant", content="I'll write it now.")
    session_store.append_event(
        session_id,
        role="assistant",
        content="",
        tool_calls=[{"id": "tc1", "name": "write_file", "args": {"path": "hello.py"}}],
    )
    session_store.append_event(
        session_id, role="tool", tool_name="write_file", content="File written."
    )

    resp = client.get(f"/api/v1/sessions/{session_id}/events")
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert len(events) == 4

    # Check event_type classification
    types = [e["event_type"] for e in events]
    assert "user_message" in types
    assert "thinking" in types
    assert "tool_call" in types
    assert "tool_result" in types


def test_v1_events_from_seq(client, session_id):
    session_store.append_event(session_id, role="user", content="first")
    session_store.append_event(session_id, role="assistant", content="second")
    session_store.append_event(session_id, role="assistant", content="third")

    # Fetch only events after seq 0
    resp = client.get(f"/api/v1/sessions/{session_id}/events?from_seq=0")
    assert resp.status_code == 200
    events = resp.json()["events"]
    # Should only have seq > 0, i.e. seqs 1 and 2
    assert all(e["seq"] > 0 for e in events)


# ---------------------------------------------------------------------------
# Session memory
# ---------------------------------------------------------------------------

def test_v1_memory_empty(client, session_id):
    resp = client.get(f"/api/v1/sessions/{session_id}/memory")
    assert resp.status_code == 200
    assert resp.json()["facts"] == []


def test_v1_memory_with_data(client, session_id):
    session_store.upsert_memory(session_id, "framework", "FastAPI")
    session_store.upsert_memory(session_id, "language", "Python")

    resp = client.get(f"/api/v1/sessions/{session_id}/memory")
    assert resp.status_code == 200
    facts = resp.json()["facts"]
    keys = {f["key"] for f in facts}
    assert "framework" in keys
    assert "language" in keys


def test_v1_memory_not_found(client):
    resp = client.get("/api/v1/sessions/nonexistent-xyz/memory")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Approve endpoint
# ---------------------------------------------------------------------------

def test_v1_approve(client, session_id):
    resp = client.post(f"/api/v1/sessions/{session_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_v1_approve_not_found(client):
    resp = client.post("/api/v1/sessions/nonexistent-xyz/approve")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_v1_delete_session(client, session_id):
    resp = client.delete(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify gone
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 404


def test_v1_delete_not_found(client):
    resp = client.delete("/api/v1/sessions/nonexistent-xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Orchestrate graph + locks
# ---------------------------------------------------------------------------

def test_v1_orchestrate_graph_empty(client, session_id):
    resp = client.get(f"/api/v1/orchestrate/{session_id}/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["nodes"] == []
    assert body["is_complete"] is False
    assert body["has_failures"] is False


def test_v1_orchestrate_graph_with_tasks(client, session_id):
    session_store.upsert_task(
        session_id, "t1", "implement feature A", worker_type="implementer", status="done"
    )
    session_store.upsert_task(
        session_id, "t2", "write tests", worker_type="tester",
        depends_on=["t1"], status="running"
    )

    resp = client.get(f"/api/v1/orchestrate/{session_id}/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 2
    assert body["is_complete"] is False  # t2 is still running
    assert body["has_failures"] is False


def test_v1_orchestrate_graph_complete(client, session_id):
    session_store.upsert_task(session_id, "t1", "task A", status="done")
    session_store.upsert_task(session_id, "t2", "task B", status="done")

    resp = client.get(f"/api/v1/orchestrate/{session_id}/graph")
    assert resp.json()["is_complete"] is True
    assert resp.json()["has_failures"] is False


def test_v1_orchestrate_graph_with_failure(client, session_id):
    session_store.upsert_task(session_id, "t1", "task A", status="failed")
    session_store.upsert_task(session_id, "t2", "task B", status="done")

    resp = client.get(f"/api/v1/orchestrate/{session_id}/graph")
    body = resp.json()
    assert body["is_complete"] is True
    assert body["has_failures"] is True


def test_v1_orchestrate_locks_empty(client, session_id):
    resp = client.get(f"/api/v1/orchestrate/{session_id}/locks")
    assert resp.status_code == 200
    assert resp.json()["locks"] == []


def test_v1_orchestrate_locks_with_data(client, session_id):
    session_store.acquire_file_lock(session_id, "src/auth.py", "worker-1")
    session_store.acquire_file_lock(session_id, "src/models.py", "worker-2")

    resp = client.get(f"/api/v1/orchestrate/{session_id}/locks")
    assert resp.status_code == 200
    locks = resp.json()["locks"]
    paths = {lk["file_path"] for lk in locks}
    assert "src/auth.py" in paths
    assert "src/models.py" in paths


def test_v1_orchestrate_not_found(client):
    resp = client.get("/api/v1/orchestrate/nonexistent-xyz/graph")
    assert resp.status_code == 404
    resp = client.get("/api/v1/orchestrate/nonexistent-xyz/locks")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session appears as orchestrate after tasks are added
# ---------------------------------------------------------------------------

def test_v1_session_is_orchestrate_flag(client, session_id):
    # Initially not orchestrate
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.json()["is_orchestrate"] is False

    # Add a task → becomes orchestrate
    session_store.upsert_task(session_id, "t1", "do something", status="pending")
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.json()["is_orchestrate"] is True


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def test_v1_metrics(client):
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_tokens" in body
    assert "total_cost_usd" in body
    assert "sessions_count" in body
    assert "active_sessions" in body
    assert "by_model" in body
    assert isinstance(body["by_model"], list)
    assert "by_hour" in body
    assert isinstance(body["by_hour"], list)


def test_v1_metrics_all_periods(client):
    for period in ("1h", "24h", "7d", "30d"):
        resp = client.get(f"/api/v1/metrics?period={period}")
        assert resp.status_code == 200
        assert resp.json()["period"] == period


def test_v1_metrics_by_hour_length(client):
    resp = client.get("/api/v1/metrics?period=24h")
    assert resp.status_code == 200
    # 24h period should have 24 hour buckets
    assert len(resp.json()["by_hour"]) == 24


def test_v1_metrics_counts_sessions(client, session_id):
    resp = client.get("/api/v1/metrics?period=24h")
    # sessions_count should be >= 1 since we created one
    assert resp.json()["sessions_count"] >= 1


# ---------------------------------------------------------------------------
# Legacy tools endpoint
# ---------------------------------------------------------------------------

def test_legacy_tools(client):
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert "tools" in body
    assert isinstance(body["tools"], list)
    assert body["count"] >= 10
    names = [t["name"] for t in body["tools"]]
    assert "read_file" in names
    assert "run_shell" in names


# ---------------------------------------------------------------------------
# Unknown route
# ---------------------------------------------------------------------------

def test_unknown_route(client):
    resp = client.get("/api/v1/nonexistent-endpoint")
    assert resp.status_code == 404
    body = resp.json()
    # Custom error handler returns {"error": "..."}
    assert "error" in body or "detail" in body
