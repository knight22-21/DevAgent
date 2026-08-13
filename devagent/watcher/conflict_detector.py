"""Cross-issue conflict detector for F3 Repo Health Monitor."""

from __future__ import annotations

from datetime import datetime, timezone

from devagent.core.models import CrossIssueConflict, WatcherAnalysis


class CrossIssueConflictDetector:
    """Detects files touched by more than one open issue."""

    def detect(self, analyses: list[WatcherAnalysis]) -> list[CrossIssueConflict]:
        """
        Given all WatcherAnalysis objects for a repo, finds files
        that are touched by more than one issue.

        Returns a list of CrossIssueConflict objects, one per conflicted file,
        sorted high → low severity.
        """
        if len(analyses) < 2:
            return []

        # Build file → [analyses that touch it] mapping
        file_to_analyses: dict[str, list[WatcherAnalysis]] = {}
        for analysis in analyses:
            for file_path in analysis.touched_files:
                file_to_analyses.setdefault(file_path, []).append(analysis)

        conflicts: list[CrossIssueConflict] = []
        for file_path, touching in file_to_analyses.items():
            if len(touching) < 2:
                continue

            severity = self._compute_severity(file_path, touching)
            conflict = CrossIssueConflict(
                file_path=file_path,
                issue_numbers=[a.issue_number for a in touching],
                issue_titles={a.issue_number: a.issue_title for a in touching},
                severity=severity,
                detected_at=datetime.now(timezone.utc),
            )
            conflicts.append(conflict)

        # Sort: high first, then by number of issues touching the file (desc)
        conflicts.sort(
            key=lambda c: (
                {"high": 0, "medium": 1, "low": 2}[c.severity],
                -len(c.issue_numbers),
            )
        )
        return conflicts

    def _compute_severity(
        self, file_path: str, touching_analyses: list[WatcherAnalysis]
    ) -> str:
        """
        Severity rules:
        - HIGH:   file appears in conflicted_files of at least one analysis
        - MEDIUM: file is not in conflicted_files but appears in ≥2 issues
                  with PARTIALLY_EXISTS / EXTEND / CONFLICTED status
        - LOW:    file touched by 2+ issues with no other signals
        """
        for analysis in touching_analyses:
            if file_path in analysis.conflicted_files:
                return "high"

        extension_count = 0
        for analysis in touching_analyses:
            for req_summary in analysis.requirement_summaries:
                if file_path in req_summary.get("files", []):
                    if req_summary.get("status") in (
                        "PARTIALLY_EXISTS", "EXTEND", "CONFLICTED"
                    ):
                        extension_count += 1
                        break

        if extension_count >= 2:
            return "medium"

        return "low"
