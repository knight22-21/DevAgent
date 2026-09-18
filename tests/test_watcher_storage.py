"""Tests for the F3 watcher storage module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pytest_asyncio

from devagent.core.models import IssueComplexity, WatcherAnalysis


@pytest_asyncio.fixture
async def watcher_db(tmp_path):
    """Provides a temporary watcher database for tests."""
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import init_watcher_db
        await init_watcher_db()
        yield db_path


@pytest.fixture
def sample_analysis():
    return WatcherAnalysis(
        owner="myorg",
        repo="backend",
        issue_number=142,
        issue_title="Add OAuth2 login with Google",
        issue_url="https://github.com/myorg/backend/issues/142",
        analysed_at=datetime.now(UTC),
        requirements_count=4,
        conflicts_count=1,
        complexity=IssueComplexity.MEDIUM,
        touched_files=["auth/session.py", "auth/routes.py", "models/user.py"],
        conflicted_files=["auth/session.py"],
        requirement_summaries=[],
        full_report_available=False,
    )


@pytest.mark.asyncio
async def test_register_and_retrieve_repo(tmp_path):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import init_watcher_db, register_repo
        await init_watcher_db()
        watched = await register_repo("myorg", "backend", 30, [])
        assert watched.owner == "myorg"
        assert watched.repo == "backend"
        assert watched.check_interval_minutes == 30
        assert watched.is_active is True


@pytest.mark.asyncio
async def test_register_idempotent(tmp_path):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import get_watched_repo, init_watcher_db, register_repo
        await init_watcher_db()
        await register_repo("myorg", "backend", 30, [])
        await register_repo("myorg", "backend", 60, ["feature"])  # update
        repo = await get_watched_repo("myorg", "backend")
        assert repo is not None
        assert repo.check_interval_minutes == 60


@pytest.mark.asyncio
async def test_deactivate_repo(tmp_path):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import (
            deactivate_repo,
            init_watcher_db,
            list_watched_repos,
            register_repo,
        )
        await init_watcher_db()
        await register_repo("myorg", "backend", 30, [])
        await deactivate_repo("myorg", "backend")
        repos = await list_watched_repos()
        assert len(repos) == 0  # list_watched_repos returns only active


@pytest.mark.asyncio
async def test_save_and_retrieve_analysis(tmp_path, sample_analysis):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import get_analysis, init_watcher_db, save_analysis
        await init_watcher_db()
        await save_analysis(sample_analysis)
        retrieved = await get_analysis("myorg", "backend", 142)
        assert retrieved is not None
        assert retrieved.issue_number == 142
        assert retrieved.issue_title == sample_analysis.issue_title
        assert retrieved.complexity == IssueComplexity.MEDIUM
        assert "auth/session.py" in retrieved.conflicted_files


@pytest.mark.asyncio
async def test_get_analysed_issue_numbers(tmp_path, sample_analysis):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import (
            get_analysed_issue_numbers,
            init_watcher_db,
            save_analysis,
        )
        await init_watcher_db()
        await save_analysis(sample_analysis)
        numbers = await get_analysed_issue_numbers("myorg", "backend")
        assert 142 in numbers


@pytest.mark.asyncio
async def test_save_analysis_is_idempotent(tmp_path, sample_analysis):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import (
            get_all_analyses_for_repo,
            init_watcher_db,
            save_analysis,
        )
        await init_watcher_db()
        await save_analysis(sample_analysis)
        await save_analysis(sample_analysis)  # second save should not duplicate
        analyses = await get_all_analyses_for_repo("myorg", "backend")
        assert len(analyses) == 1


@pytest.mark.asyncio
async def test_mark_full_report_available(tmp_path, sample_analysis):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import (
            get_analysis,
            init_watcher_db,
            mark_full_report_available,
            save_analysis,
        )
        await init_watcher_db()
        await save_analysis(sample_analysis)
        await mark_full_report_available("myorg", "backend", 142)
        retrieved = await get_analysis("myorg", "backend", 142)
        assert retrieved.full_report_available is True


@pytest.mark.asyncio
async def test_save_cross_conflicts_for_repo(tmp_path):
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.core.models import CrossIssueConflict
        from devagent.watcher.storage import (
            get_cross_conflicts,
            init_watcher_db,
            save_cross_conflicts_for_repo,
        )
        await init_watcher_db()
        conflict = CrossIssueConflict(
            file_path="auth/session.py",
            issue_numbers=[142, 143],
            issue_titles={142: "Issue A", 143: "Issue B"},
            severity="high",
            detected_at=datetime.now(UTC),
        )
        await save_cross_conflicts_for_repo("myorg", "backend", [conflict])
        conflicts = await get_cross_conflicts("myorg", "backend")
        assert len(conflicts) == 1
        assert conflicts[0].file_path == "auth/session.py"
        assert conflicts[0].severity == "high"
        assert set(conflicts[0].issue_numbers) == {142, 143}
