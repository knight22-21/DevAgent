"""WatcherChecker: fetches new issues and runs lightweight analysis per issue."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from devagent.core.config import DevAgentConfig
from devagent.core.models import IssueComplexity, WatchedRepo, WatcherAnalysis
from devagent.mcp.manager import MCPManager
from devagent.watcher.storage import (
    get_analysed_issue_numbers,
    log_check_run,
    save_analysis,
    update_last_checked,
)


class WatcherChecker:
    """Performs a single check cycle for one watched repo."""

    def __init__(self, config: DevAgentConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root

    async def run_check(
        self,
        watched_repo: WatchedRepo,
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> list[WatcherAnalysis]:
        """
        Runs one check cycle for a watched repo.
        Returns list of new WatcherAnalysis objects created this run.
        """
        start_time = time.monotonic()
        new_analyses: list[WatcherAnalysis] = []

        async with MCPManager(self.config, self.project_root) as manager:
            # Step 1: Find new issues
            new_issues = await self._fetch_new_issues(manager, watched_repo)

            if not new_issues:
                await update_last_checked(
                    watched_repo.owner, watched_repo.repo, datetime.now(timezone.utc)
                )
                return []

            # Step 2: Analyse each new issue (respect limit)
            issues_to_analyse = new_issues[: self.config.watcher.max_issues_per_check]

            for issue in issues_to_analyse:
                if progress_callback:
                    progress_callback(issue["number"], issue["title"], "analysing")

                analysis = await self._analyse_issue(manager, watched_repo, issue)
                if analysis:
                    await save_analysis(analysis)
                    new_analyses.append(analysis)

                    if progress_callback:
                        progress_callback(issue["number"], issue["title"], "done")

            # Step 3: Update timestamp
            await update_last_checked(
                watched_repo.owner, watched_repo.repo, datetime.now(timezone.utc)
            )

            # Step 4: Log check run
            duration = time.monotonic() - start_time
            await log_check_run(
                watched_repo.owner,
                watched_repo.repo,
                len(new_analyses),
                0,
                duration,
            )

        return new_analyses

    async def _fetch_new_issues(
        self, manager: MCPManager, watched_repo: WatchedRepo
    ) -> list[dict]:
        """Fetches GitHub issues opened since last_checked_at."""
        github = manager.github
        if github is None:
            return []

        since = watched_repo.last_checked_at
        issues = await github.list_issues(
            owner=watched_repo.owner,
            repo=watched_repo.repo,
            state="open",
            since=since,
            labels=watched_repo.issue_filters if watched_repo.issue_filters else None,
        )

        # Keep only truly NEW issues (not just updated ones)
        if since:
            issues = [i for i in issues if i.get("created_at", "") >= since.isoformat()]

        # Skip already-analysed issues
        analysed_numbers = await get_analysed_issue_numbers(
            watched_repo.owner, watched_repo.repo
        )
        return [i for i in issues if i["number"] not in analysed_numbers]

    async def _analyse_issue(
        self,
        manager: MCPManager,
        watched_repo: WatchedRepo,
        issue: dict,
    ) -> WatcherAnalysis | None:
        """
        Runs SpecParserAgent + CodeInventoryAgent for one issue.
        Returns WatcherAnalysis. Does NOT run GapReportAgent (for speed).
        Returns None if analysis fails — watcher continues with next issue.
        """
        try:
            from devagent.agents.spec_parser import SpecParserAgent
            from devagent.agents.code_inventory import CodeInventoryAgent

            spec_text = f"{issue['title']}\n\n{issue.get('body') or ''}"

            # Build initial state dict for agents
            state: dict = {
                "spec_text": spec_text,
                "spec_source": f"github_issue #{issue['number']}",
                "search_context": "",
                "requirements": [],
                "edge_cases": [],
                "data_models": [],
                "api_changes": [],
                "requirement_analyses": [],
                "effort_estimate": None,
                "implementation_order": [],
                "gap_report": None,
            }

            # Run SpecParserAgent
            spec_parser = SpecParserAgent(self.config, manager)
            state = await spec_parser.app.ainvoke(state)

            if not state.get("requirements"):
                return None

            # Run CodeInventoryAgent
            code_inventory = CodeInventoryAgent(self.config, manager)
            state = await code_inventory.app.ainvoke(state)

            return self._build_analysis(watched_repo, issue, state)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "watcher_analysis_failed issue=%s error=%s",
                issue.get("number"),
                str(e),
            )
            return None

    def _build_analysis(
        self,
        watched_repo: WatchedRepo,
        issue: dict,
        state: dict,
    ) -> WatcherAnalysis:
        """Builds a WatcherAnalysis from a completed pipeline state dict."""
        touched_files: set[str] = set()
        conflicted_files: set[str] = set()
        conflicts_count = 0
        req_summaries: list[dict] = []

        for ra in state.get("requirement_analyses", []):
            touched_files.update(ra.matched_files)
            if ra.status.value == "CONFLICTED":
                conflicts_count += 1
                conflicted_files.update(ra.matched_files)
                if ra.conflict_details:
                    conflicted_files.update(ra.conflict_details.affected_files)

            req_summaries.append(
                {
                    "id": ra.requirement.id,
                    "description": ra.requirement.description,
                    "status": ra.status.value,
                    "files": ra.matched_files[:5],
                }
            )

        req_count = len(state.get("requirements", []))
        files_count = len(touched_files)

        if conflicts_count >= 3 or req_count >= 7 or files_count >= 10:
            complexity = IssueComplexity.HIGH
        elif conflicts_count >= 1 or req_count >= 4:
            complexity = IssueComplexity.MEDIUM
        else:
            complexity = IssueComplexity.LOW

        return WatcherAnalysis(
            owner=watched_repo.owner,
            repo=watched_repo.repo,
            issue_number=issue["number"],
            issue_title=issue["title"],
            issue_url=issue.get(
                "url",
                f"https://github.com/{watched_repo.owner}/{watched_repo.repo}/issues/{issue['number']}",
            ),
            analysed_at=datetime.now(timezone.utc),
            requirements_count=req_count,
            conflicts_count=conflicts_count,
            complexity=complexity,
            touched_files=sorted(touched_files),
            conflicted_files=sorted(conflicted_files),
            requirement_summaries=req_summaries,
            full_report_available=False,
        )
