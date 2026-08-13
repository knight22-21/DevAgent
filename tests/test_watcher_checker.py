"""Tests for WatcherChecker._build_analysis (unit tested without MCP)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from devagent.core.models import IssueComplexity, RequirementStatus
from devagent.watcher.checker import WatcherChecker


def _make_req_analysis(status: str, files: list[str], conflicted: list[str] | None = None):
    ra = MagicMock()
    ra.status = MagicMock()
    ra.status.value = status
    ra.matched_files = files
    ra.conflict_details = None
    if conflicted:
        ra.conflict_details = MagicMock()
        ra.conflict_details.affected_files = conflicted
    ra.requirement = MagicMock()
    ra.requirement.id = "REQ-1"
    ra.requirement.description = "A requirement"
    return ra


def _make_watched_repo(owner="myorg", repo="backend"):
    from devagent.core.models import WatchedRepo
    return WatchedRepo(
        owner=owner,
        repo=repo,
        registered_at=datetime.now(timezone.utc),
        check_interval_minutes=30,
    )


def _make_issue(number=142, title="Test Issue"):
    return {
        "number": number,
        "title": title,
        "body": "Some body",
        "url": f"https://github.com/myorg/backend/issues/{number}",
    }


def test_build_analysis_low_complexity():
    checker = WatcherChecker(MagicMock(), MagicMock())
    state = {
        "requirements": [MagicMock(), MagicMock()],
        "requirement_analyses": [
            _make_req_analysis("FULLY_EXISTS", ["file_a.py"]),
            _make_req_analysis("MISSING", ["file_b.py"]),
        ],
    }
    analysis = checker._build_analysis(_make_watched_repo(), _make_issue(), state)
    assert analysis.complexity == IssueComplexity.LOW
    assert analysis.conflicts_count == 0
    assert "file_a.py" in analysis.touched_files
    assert len(analysis.conflicted_files) == 0


def test_build_analysis_medium_complexity_by_reqs():
    checker = WatcherChecker(MagicMock(), MagicMock())
    reqs = [MagicMock() for _ in range(4)]
    state = {
        "requirements": reqs,
        "requirement_analyses": [
            _make_req_analysis("FULLY_EXISTS", [f"file_{i}.py"])
            for i in range(4)
        ],
    }
    analysis = checker._build_analysis(_make_watched_repo(), _make_issue(), state)
    assert analysis.complexity == IssueComplexity.MEDIUM
    assert analysis.requirements_count == 4


def test_build_analysis_high_complexity_by_conflicts():
    checker = WatcherChecker(MagicMock(), MagicMock())
    reqs = [MagicMock() for _ in range(3)]
    state = {
        "requirements": reqs,
        "requirement_analyses": [
            _make_req_analysis("CONFLICTED", ["file_a.py"], conflicted=["file_a.py"]),
            _make_req_analysis("CONFLICTED", ["file_b.py"], conflicted=["file_b.py"]),
            _make_req_analysis("CONFLICTED", ["file_c.py"], conflicted=["file_c.py"]),
        ],
    }
    analysis = checker._build_analysis(_make_watched_repo(), _make_issue(), state)
    assert analysis.complexity == IssueComplexity.HIGH
    assert analysis.conflicts_count == 3
    assert set(analysis.conflicted_files) == {"file_a.py", "file_b.py", "file_c.py"}


def test_build_analysis_high_complexity_by_files():
    checker = WatcherChecker(MagicMock(), MagicMock())
    state = {
        "requirements": [MagicMock()],
        "requirement_analyses": [
            _make_req_analysis("MISSING", [f"file_{i}.py"])
            for i in range(11)  # 11 unique files → HIGH
        ],
    }
    analysis = checker._build_analysis(_make_watched_repo(), _make_issue(), state)
    assert analysis.complexity == IssueComplexity.HIGH
    assert len(analysis.touched_files) == 11


def test_build_analysis_touched_files_deduplicated():
    checker = WatcherChecker(MagicMock(), MagicMock())
    state = {
        "requirements": [MagicMock(), MagicMock()],
        "requirement_analyses": [
            _make_req_analysis("FULLY_EXISTS", ["shared.py", "a.py"]),
            _make_req_analysis("EXTEND", ["shared.py", "b.py"]),
        ],
    }
    analysis = checker._build_analysis(_make_watched_repo(), _make_issue(), state)
    # shared.py should appear only once
    assert analysis.touched_files.count("shared.py") == 1
    assert len(analysis.touched_files) == 3  # shared.py, a.py, b.py
