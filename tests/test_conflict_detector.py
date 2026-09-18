"""Tests for the F3 CrossIssueConflictDetector."""

from __future__ import annotations

from datetime import UTC, datetime

from devagent.core.models import IssueComplexity, WatcherAnalysis
from devagent.watcher.conflict_detector import CrossIssueConflictDetector


def make_analysis(
    issue_number: int,
    touched_files: list[str],
    conflicted_files: list[str] | None = None,
    req_summaries: list[dict] | None = None,
) -> WatcherAnalysis:
    conflicted = conflicted_files or []
    return WatcherAnalysis(
        owner="myorg",
        repo="backend",
        issue_number=issue_number,
        issue_title=f"Issue {issue_number}",
        issue_url=f"https://github.com/myorg/backend/issues/{issue_number}",
        analysed_at=datetime.now(UTC),
        requirements_count=2,
        conflicts_count=len(conflicted),
        complexity=IssueComplexity.LOW,
        touched_files=touched_files,
        conflicted_files=conflicted,
        requirement_summaries=req_summaries or [],
    )


def test_no_conflicts_when_no_overlap():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["auth/login.py", "auth/session.py"]),
        make_analysis(2, ["api/routes.py", "models/user.py"]),
    ]
    conflicts = detector.detect(analyses)
    assert len(conflicts) == 0


def test_detects_file_overlap():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["auth/session.py", "auth/login.py"]),
        make_analysis(2, ["auth/session.py", "api/routes.py"]),
    ]
    conflicts = detector.detect(analyses)
    assert len(conflicts) == 1
    assert conflicts[0].file_path == "auth/session.py"
    assert set(conflicts[0].issue_numbers) == {1, 2}


def test_high_severity_when_conflicted_file():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["auth/session.py"], conflicted_files=["auth/session.py"]),
        make_analysis(2, ["auth/session.py"]),
    ]
    conflicts = detector.detect(analyses)
    assert conflicts[0].severity == "high"


def test_medium_severity_when_extension_overlap():
    detector = CrossIssueConflictDetector()
    summaries_1 = [{"id": "REQ-1", "description": "x", "status": "EXTEND", "files": ["auth/session.py"]}]
    summaries_2 = [{"id": "REQ-1", "description": "x", "status": "PARTIALLY_EXISTS", "files": ["auth/session.py"]}]
    analyses = [
        make_analysis(1, ["auth/session.py"], req_summaries=summaries_1),
        make_analysis(2, ["auth/session.py"], req_summaries=summaries_2),
    ]
    conflicts = detector.detect(analyses)
    assert conflicts[0].severity == "medium"


def test_low_severity_when_plain_overlap():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["auth/session.py"]),
        make_analysis(2, ["auth/session.py"]),
    ]
    conflicts = detector.detect(analyses)
    assert conflicts[0].severity == "low"


def test_three_issues_touching_same_file():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["auth/session.py"]),
        make_analysis(2, ["auth/session.py"]),
        make_analysis(3, ["auth/session.py"]),
    ]
    conflicts = detector.detect(analyses)
    assert len(conflicts) == 1
    assert len(conflicts[0].issue_numbers) == 3


def test_single_analysis_no_conflicts():
    detector = CrossIssueConflictDetector()
    analyses = [make_analysis(1, ["auth/session.py"])]
    conflicts = detector.detect(analyses)
    assert len(conflicts) == 0


def test_empty_analyses_no_conflicts():
    detector = CrossIssueConflictDetector()
    assert detector.detect([]) == []


def test_high_severity_sorted_first():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["low_file.py", "high_file.py"], conflicted_files=["high_file.py"]),
        make_analysis(2, ["low_file.py", "high_file.py"]),
    ]
    conflicts = detector.detect(analyses)
    # high_file.py should be first (high severity)
    assert conflicts[0].severity == "high"
    assert conflicts[0].file_path == "high_file.py"


def test_issue_titles_populated():
    detector = CrossIssueConflictDetector()
    analyses = [
        make_analysis(1, ["auth/session.py"]),
        make_analysis(2, ["auth/session.py"]),
    ]
    conflicts = detector.detect(analyses)
    assert conflicts[0].issue_titles[1] == "Issue 1"
    assert conflicts[0].issue_titles[2] == "Issue 2"
