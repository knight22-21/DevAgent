"""SQLite-backed session persistence.

Schema:
  sessions       -- one row per session (id, project, model, created_at, updated_at, metadata)
  events         -- append-only event log (turn messages, tool calls, results)
  memory_items   -- structured session memory (key-value with type/scope)
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from devagent.core.storage import get_sessions_db_path


def _conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_sessions_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(db_path: Path | None = None) -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    with _conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                project     TEXT NOT NULL DEFAULT '',
                model       TEXT NOT NULL DEFAULT '',
                provider    TEXT NOT NULL DEFAULT '',
                title       TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                metadata    TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                seq         INTEGER NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                tool_calls  TEXT NOT NULL DEFAULT '[]',
                tool_call_id TEXT NOT NULL DEFAULT '',
                tool_name   TEXT NOT NULL DEFAULT '',
                tokens_in   INTEGER NOT NULL DEFAULT 0,
                tokens_out  INTEGER NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, seq);

            CREATE TABLE IF NOT EXISTS memory_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                scope       TEXT NOT NULL DEFAULT 'session',
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                item_type   TEXT NOT NULL DEFAULT 'fact',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                UNIQUE(session_id, scope, key),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
        """)


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

def create_session(
    session_id: str,
    project: str = "",
    model: str = "",
    provider: str = "",
    title: str = "",
    metadata: dict | None = None,
    db_path: Path | None = None,
) -> None:
    now = time.time()
    with _conn(db_path) as conn:
        conn.execute(
            """INSERT INTO sessions (id, project, model, provider, title, created_at, updated_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, project, model, provider, title, now, now, json.dumps(metadata or {})),
        )


def get_session(session_id: str, db_path: Path | None = None) -> dict | None:
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["metadata"] = json.loads(d["metadata"])
    return d


def update_session(
    session_id: str,
    title: str | None = None,
    metadata: dict | None = None,
    db_path: Path | None = None,
) -> None:
    now = time.time()
    with _conn(db_path) as conn:
        if title is not None:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, session_id),
            )
        if metadata is not None:
            conn.execute(
                "UPDATE sessions SET metadata = ?, updated_at = ? WHERE id = ?",
                (json.dumps(metadata), now, session_id),
            )
        if title is None and metadata is None:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )


def list_sessions(limit: int = 50, db_path: Path | None = None) -> list[dict]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"])
        result.append(d)
    return result


def delete_session(session_id: str, db_path: Path | None = None) -> None:
    with _conn(db_path) as conn:
        conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM memory_items WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


# ---------------------------------------------------------------------------
# Event log (messages + tool calls)
# ---------------------------------------------------------------------------

def append_event(
    session_id: str,
    role: str,
    content: str = "",
    tool_calls: list[dict] | None = None,
    tool_call_id: str = "",
    tool_name: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    db_path: Path | None = None,
) -> int:
    """Append one event; returns its seq number."""
    now = time.time()
    with _conn(db_path) as conn:
        cur = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM events WHERE session_id = ?",
            (session_id,),
        )
        seq = cur.fetchone()[0]
        conn.execute(
            """INSERT INTO events
               (session_id, seq, role, content, tool_calls, tool_call_id, tool_name,
                tokens_in, tokens_out, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, seq, role, content,
                json.dumps(tool_calls or []),
                tool_call_id, tool_name,
                tokens_in, tokens_out, now,
            ),
        )
        return seq


def get_events(session_id: str, db_path: Path | None = None) -> list[dict]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["tool_calls"] = json.loads(d["tool_calls"])
        result.append(d)
    return result


def get_token_totals(session_id: str, db_path: Path | None = None) -> dict[str, int]:
    with _conn(db_path) as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0)
               FROM events WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
    return {"tokens_in": row[0], "tokens_out": row[1]}


# ---------------------------------------------------------------------------
# Structured memory
# ---------------------------------------------------------------------------

def upsert_memory(
    session_id: str,
    key: str,
    value: Any,
    scope: str = "session",
    item_type: str = "fact",
    db_path: Path | None = None,
) -> None:
    now = time.time()
    with _conn(db_path) as conn:
        conn.execute(
            """INSERT INTO memory_items (session_id, scope, key, value, item_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, scope, key)
               DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (session_id, scope, key, json.dumps(value), item_type, now, now),
        )


def get_memory(
    session_id: str,
    scope: str = "session",
    db_path: Path | None = None,
) -> dict[str, Any]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT key, value FROM memory_items WHERE session_id = ? AND scope = ?",
            (session_id, scope),
        ).fetchall()
    return {row["key"]: json.loads(row["value"]) for row in rows}


def delete_memory_key(
    session_id: str,
    key: str,
    scope: str = "session",
    db_path: Path | None = None,
) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            "DELETE FROM memory_items WHERE session_id = ? AND scope = ? AND key = ?",
            (session_id, scope, key),
        )
