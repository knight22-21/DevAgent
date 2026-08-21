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
        """Runs one check cycle for a watched repo.

        Returns list of new WatcherAnalysis objects created this run.
        """
        start_time = time.monotonic()
        new_analyses: list[WatcherAnalysis] = []

        async with MCPManager(self.config, self.project_root) as manager:
            new_issues = await self._fetch_new_issues(manager, watched_repo)

            if not new_issues:
                await update_last_checked(
                    watched_repo.owner, watched_repo.repo, datetime.now(timezone.utc)
                )
                return []

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

            await update_last_checked(
                watched_repo.owner, watched_repo.repo, datetime.now(timezone.utc)
            )

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

        if since:
            issues = [i for i in issues if i.get("created_at", "") >= since.isoformat()]

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
        """Run a one-shot agent analysis for a single issue."""
        import asyncio
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None,
                self._agent_analyse_issue,
                watched_repo,
                issue,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "watcher_analysis_failed issue=%s error=%s",
                issue.get("number"),
                str(exc),
            )
            return None

    def _agent_analyse_issue(
        self,
        watched_repo: WatchedRepo,
        issue: dict,
    ) -> WatcherAnalysis:
        """Sync agent analysis — runs in a thread via run_in_executor."""
        from devagent.agent.flows import DevAgentSession

        num = issue["number"]
        issue_url = issue.get(
            "html_url",
            f"https://github.com/{watched_repo.owner}/{watched_repo.repo}/issues/{num}",
        )
        body_preview = (issue.get("body") or "")[:1000]

        prompt = (
            f"Analyze GitHub issue #{num}: {issue['title']}\n\n"
            f"Repository: {watched_repo.owner}/{watched_repo.repo}\n"
            f"Body:\n{body_preview}\n\n"
            "Provide a concise analysis:\n"
            "1. Effort estimate (trivial / small / medium / large)\n"
            "2. Key files or modules likely affected\n"
            "3. Implementation approach in 2-3 sentences\n"
            "4. Any risks or blockers\n\n"
            "Use CodePrism tools if the project is indexed to identify affected areas. "
            "Keep the total response under 300 words."
        )

        try:
            session = DevAgentSession(self.config, self.project_root)
            analysis_text = session.run_message(prompt, quiet=True)
        except Exception as exc:
            analysis_text = f"(agent analysis unavailable: {exc})"

        # Heuristic complexity from analysis text
        low = analysis_text.lower()
        if any(w in low for w in ["large", "significant", "major", "complex", ">2d", "2+ days"]):
            complexity = IssueComplexity.HIGH
        elif any(w in low for w in ["medium", "moderate", "1-2 day", "half day", "small"]):
            complexity = IssueComplexity.MEDIUM
        else:
            complexity = IssueComplexity.LOW

        return WatcherAnalysis(
            owner=watched_repo.owner,
            repo=watched_repo.repo,
            issue_number=num,
            issue_title=issue["title"],
            issue_url=issue_url,
            analysed_at=datetime.now(timezone.utc),
            requirements_count=1,
            conflicts_count=0,
            complexity=complexity,
            touched_files=[],
            conflicted_files=[],
            requirement_summaries=[analysis_text[:500]],
            full_report_available=True,
        )
