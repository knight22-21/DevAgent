"""SQLite storage layer for the F3 Repo Health Monitor watcher."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from devagent.core.models import (
    CrossIssueConflict,
    IssueComplexity,
    WatchedRepo,
    WatcherAnalysis,
)
from devagent.core.storage import get_watcher_db_path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watched_repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    last_checked_at TEXT,
    check_interval_minutes INTEGER NOT NULL DEFAULT 30,
    is_active INTEGER NOT NULL DEFAULT 1,
    issue_filters TEXT NOT NULL DEFAULT '[]',
    UNIQUE(owner, repo)
);

CREATE TABLE IF NOT EXISTS watcher_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    issue_title TEXT NOT NULL,
    issue_url TEXT NOT NULL,
    analysed_at TEXT NOT NULL,
    requirements_count INTEGER NOT NULL,
    conflicts_count INTEGER NOT NULL,
    complexity TEXT NOT NULL,
    touched_files TEXT NOT NULL,
    conflicted_files TEXT NOT NULL,
    requirement_summaries TEXT NOT NULL,
    full_report_available INTEGER NOT NULL DEFAULT 0,
    UNIQUE(owner, repo, issue_number)
);

CREATE TABLE IF NOT EXISTS cross_issue_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    file_path TEXT NOT NULL,
    issue_numbers TEXT NOT NULL,
    issue_titles TEXT NOT NULL,
    severity TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS check_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    run_at TEXT NOT NULL,
    new_issues_count INTEGER NOT NULL,
    cross_conflicts_count INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analyses_repo ON watcher_analyses(owner, repo);
CREATE INDEX IF NOT EXISTS idx_analyses_issue ON watcher_analyses(owner, repo, issue_number);
CREATE INDEX IF NOT EXISTS idx_conflicts_repo ON cross_issue_conflicts(owner, repo);
CREATE INDEX IF NOT EXISTS idx_conflicts_file ON cross_issue_conflicts(owner, repo, file_path);
"""


def _db_path() -> Path:
    """Indirection so tests can patch this single call-site."""
    return get_watcher_db_path()


async def init_watcher_db() -> None:
    """Creates the watcher.db and all tables if they don't exist."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def register_repo(
    owner: str, repo: str, interval_minutes: int, labels: list[str]
) -> WatchedRepo:
    """Inserts or updates a watched repo record. Idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    filters_json = json.dumps(labels)

    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            INSERT INTO watched_repos
                (owner, repo, registered_at, check_interval_minutes, is_active, issue_filters)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(owner, repo) DO UPDATE SET
                check_interval_minutes = excluded.check_interval_minutes,
                issue_filters = excluded.issue_filters,
                is_active = 1
            """,
            (owner, repo, now, interval_minutes, filters_json),
        )
        await db.commit()

    result = await get_watched_repo(owner, repo)
    assert result is not None
    return result


async def get_watched_repo(owner: str, repo: str) -> WatchedRepo | None:
    """Returns the WatchedRepo if registered, None otherwise."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM watched_repos WHERE owner=? AND repo=?", (owner, repo)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return _row_to_watched_repo(row)


async def list_watched_repos() -> list[WatchedRepo]:
    """Returns all active watched repos."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM watched_repos WHERE is_active=1 ORDER BY registered_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_watched_repo(r) for r in rows]


async def update_last_checked(owner: str, repo: str, checked_at: datetime) -> None:
    """Updates last_checked_at for a repo after a successful check run."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "UPDATE watched_repos SET last_checked_at=? WHERE owner=? AND repo=?",
            (checked_at.isoformat(), owner, repo),
        )
        await db.commit()


async def deactivate_repo(owner: str, repo: str) -> None:
    """Marks a repo as inactive (stop watching). Does not delete data."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "UPDATE watched_repos SET is_active=0 WHERE owner=? AND repo=?",
            (owner, repo),
        )
        await db.commit()


async def save_analysis(analysis: WatcherAnalysis) -> None:
    """Saves a WatcherAnalysis. Upserts if the issue_number already exists."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            INSERT INTO watcher_analyses
                (owner, repo, issue_number, issue_title, issue_url, analysed_at,
                 requirements_count, conflicts_count, complexity,
                 touched_files, conflicted_files, requirement_summaries, full_report_available)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner, repo, issue_number) DO UPDATE SET
                issue_title = excluded.issue_title,
                analysed_at = excluded.analysed_at,
                requirements_count = excluded.requirements_count,
                conflicts_count = excluded.conflicts_count,
                complexity = excluded.complexity,
                touched_files = excluded.touched_files,
                conflicted_files = excluded.conflicted_files,
                requirement_summaries = excluded.requirement_summaries,
                full_report_available = excluded.full_report_available
            """,
            (
                analysis.owner,
                analysis.repo,
                analysis.issue_number,
                analysis.issue_title,
                analysis.issue_url,
                analysis.analysed_at.isoformat(),
                analysis.requirements_count,
                analysis.conflicts_count,
                analysis.complexity.value,
                json.dumps(analysis.touched_files),
                json.dumps(analysis.conflicted_files),
                json.dumps(analysis.requirement_summaries),
                int(analysis.full_report_available),
            ),
        )
        await db.commit()


async def get_analysis(owner: str, repo: str, issue_number: int) -> WatcherAnalysis | None:
    """Returns stored analysis for a specific issue."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM watcher_analyses WHERE owner=? AND repo=? AND issue_number=?",
            (owner, repo, issue_number),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return _row_to_analysis(row)


async def get_all_analyses_for_repo(owner: str, repo: str) -> list[WatcherAnalysis]:
    """Returns all stored analyses for a repo, sorted by issue_number descending."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM watcher_analyses WHERE owner=? AND repo=? ORDER BY issue_number DESC",
            (owner, repo),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_analysis(r) for r in rows]


async def get_analysed_issue_numbers(owner: str, repo: str) -> set[int]:
    """Returns the set of issue numbers already analysed."""
    async with aiosqlite.connect(_db_path()) as db:
        async with db.execute(
            "SELECT issue_number FROM watcher_analyses WHERE owner=? AND repo=?",
            (owner, repo),
        ) as cursor:
            rows = await cursor.fetchall()
    return {r[0] for r in rows}


async def save_cross_conflicts(conflicts: list[CrossIssueConflict]) -> None:
    """Saves cross-issue conflicts. Replaces all existing conflicts for the repo on each run."""
    if not conflicts:
        return

    owner = conflicts[0].file_path  # We get owner/repo from the conflict list itself
    # Actually we need owner/repo passed in. Let's grab from first conflict's issue_titles context.
    # The conflict has issue_numbers but not owner/repo. We need to infer from caller.
    # Design decision: caller must delete+insert. We'll do bulk delete by owner/repo.
    # Since we don't have owner/repo on CrossIssueConflict, we need them from outside.
    # The caller (scheduler) will call this function with the specific repo's conflicts.
    # We'll add a helper: save_cross_conflicts_for_repo(owner, repo, conflicts).
    # For now, this function is unused — use save_cross_conflicts_for_repo below.
    pass


async def save_cross_conflicts_for_repo(
    owner: str, repo: str, conflicts: list[CrossIssueConflict]
) -> None:
    """Saves cross-issue conflicts for a repo, replacing all previous ones."""
    async with aiosqlite.connect(_db_path()) as db:
        # Delete previous conflicts for this repo
        await db.execute(
            "DELETE FROM cross_issue_conflicts WHERE owner=? AND repo=?",
            (owner, repo),
        )
        # Insert new ones
        for c in conflicts:
            await db.execute(
                """
                INSERT INTO cross_issue_conflicts
                    (owner, repo, file_path, issue_numbers, issue_titles, severity, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner,
                    repo,
                    c.file_path,
                    json.dumps(c.issue_numbers),
                    json.dumps({str(k): v for k, v in c.issue_titles.items()}),
                    c.severity,
                    c.detected_at.isoformat(),
                ),
            )
        await db.commit()


async def get_cross_conflicts(owner: str, repo: str) -> list[CrossIssueConflict]:
    """Returns all current cross-issue conflicts for a repo."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cross_issue_conflicts WHERE owner=? AND repo=? AND resolved=0",
            (owner, repo),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_conflict(r) for r in rows]


async def mark_full_report_available(owner: str, repo: str, issue_number: int) -> None:
    """Sets full_report_available = True for an issue after --show is run."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            UPDATE watcher_analyses SET full_report_available=1
            WHERE owner=? AND repo=? AND issue_number=?
            """,
            (owner, repo, issue_number),
        )
        await db.commit()


async def log_check_run(
    owner: str, repo: str, new_issues: int, conflicts: int, duration: float
) -> None:
    """Appends a check run record for audit/history purposes."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            INSERT INTO check_runs (owner, repo, run_at, new_issues_count,
                cross_conflicts_count, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (owner, repo, datetime.now(timezone.utc).isoformat(), new_issues, conflicts, duration),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Row → model converters
# ---------------------------------------------------------------------------

def _row_to_watched_repo(row: aiosqlite.Row) -> WatchedRepo:
    return WatchedRepo(
        owner=row["owner"],
        repo=row["repo"],
        registered_at=datetime.fromisoformat(row["registered_at"]),
        last_checked_at=(
            datetime.fromisoformat(row["last_checked_at"]) if row["last_checked_at"] else None
        ),
        check_interval_minutes=row["check_interval_minutes"],
        is_active=bool(row["is_active"]),
        issue_filters=json.loads(row["issue_filters"]),
    )


def _row_to_analysis(row: aiosqlite.Row) -> WatcherAnalysis:
    return WatcherAnalysis(
        owner=row["owner"],
        repo=row["repo"],
        issue_number=row["issue_number"],
        issue_title=row["issue_title"],
        issue_url=row["issue_url"],
        analysed_at=datetime.fromisoformat(row["analysed_at"]),
        requirements_count=row["requirements_count"],
        conflicts_count=row["conflicts_count"],
        complexity=IssueComplexity(row["complexity"]),
        touched_files=json.loads(row["touched_files"]),
        conflicted_files=json.loads(row["conflicted_files"]),
        requirement_summaries=json.loads(row["requirement_summaries"]),
        full_report_available=bool(row["full_report_available"]),
    )


def _row_to_conflict(row: aiosqlite.Row) -> CrossIssueConflict:
    raw_titles = json.loads(row["issue_titles"])
    return CrossIssueConflict(
        file_path=row["file_path"],
        issue_numbers=json.loads(row["issue_numbers"]),
        issue_titles={int(k): v for k, v in raw_titles.items()},
        severity=row["severity"],
        detected_at=datetime.fromisoformat(row["detected_at"]),
    )
