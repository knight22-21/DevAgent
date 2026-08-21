"""High-level agent flows built on top of AgentLoop + DevAgentSession.

Each flow:
  1. Parses the input (issue URL, PR URL, repo string, CI run URL)
  2. Pre-fetches the relevant GitHub data (issue body, PR diff, run logs, …)
  3. Builds a flow-specific system prompt extension
  4. Creates a DevAgentSession and seeds it with a rich first message
  5. Drops into the interactive REPL so the user can follow up

Flows:
  run_implement  — fetch issue → CodePrism context → edit → test → PR
  run_review     — fetch PR diff → graph analysis → post inline review
  run_triage     — classify open issues by effort → post triage comments
  run_fix_ci     — read failed logs → locate code → propose fix
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

# ---------------------------------------------------------------------------
# URL parsers (issue, PR, CI run)
# ---------------------------------------------------------------------------

@dataclass
class _ParsedIssue:
    owner: str
    repo: str
    number: int
    kind: str  # "issue" | "pull"


@dataclass
class _ParsedRun:
    owner: str
    repo: str
    run_id: str


def _parse_issue_or_pr_url(url: str) -> _ParsedIssue:
    """Parse https://github.com/owner/repo/issues/N or /pull/N."""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)",
        url.strip(),
    )
    if not m:
        raise ValueError(
            f"Cannot parse GitHub issue/PR URL: {url!r}\n"
            "Expected: https://github.com/owner/repo/issues/N"
        )
    return _ParsedIssue(
        owner=m.group(1),
        repo=m.group(2),
        number=int(m.group(4)),
        kind=m.group(3),
    )


def _parse_run_url(url: str) -> _ParsedRun:
    """Parse https://github.com/owner/repo/actions/runs/RUN_ID."""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/actions/runs/(\d+)",
        url.strip(),
    )
    if not m:
        raise ValueError(
            f"Cannot parse GitHub Actions run URL: {url!r}\n"
            "Expected: https://github.com/owner/repo/actions/runs/RUN_ID"
        )
    return _ParsedRun(owner=m.group(1), repo=m.group(2), run_id=m.group(3))


def _parse_repo(repo_or_url: str) -> tuple[str, str]:
    """Accept 'owner/repo' or 'https://github.com/owner/repo'."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?$", repo_or_url.strip())
    if m:
        return m.group(1), m.group(2)
    parts = repo_or_url.strip().split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    raise ValueError(f"Cannot parse repo: {repo_or_url!r}. Use 'owner/repo'.")


# ---------------------------------------------------------------------------
# DevAgentSession — the shared agent stack
# ---------------------------------------------------------------------------

class DevAgentSession:
    """Full agent session: LLM + tools + memory + budget + security gate.

    Usage:
        session = DevAgentSession(cfg, project_root)
        session.interactive_repl(first_message="Implement issue #42 …")
    """

    def __init__(
        self,
        cfg,                          # DevAgentConfig
        project_root: str | Path,
        *,
        max_tokens: int | None = None,
        extra_system: str = "",
        resume_id: str | None = None,
    ) -> None:
        from devagent.agent.loop import AgentLoop
        from devagent.agent.system_prompt import build_system_prompt
        from devagent.core.llm import LLMClient
        from devagent.session.budget import TokenBudget
        from devagent.session.manager import SessionManager
        from devagent.session.memory import MemoryBlock
        from devagent.tools.registry import build_registry

        self._cfg = cfg
        self._project_root = Path(project_root).resolve()
        self._console = Console()
        self.security_log: list = []

        # ── Session ──────────────────────────────────────────────────
        mgr = SessionManager()
        if resume_id:
            sessions = mgr.list(limit=200)
            match = next((s for s in sessions if s["id"].startswith(resume_id)), None)
            if not match:
                raise ValueError(f"Session not found: {resume_id}")
            session_id = match["id"]
        else:
            session_id = mgr.new(
                project=str(self._project_root),
                model=cfg.llm.model,
                provider=cfg.llm.provider,
            )
        self._mgr = mgr
        self.session_id = session_id

        # ── CodePrism (optional) ─────────────────────────────────────
        cp_client = None
        try:
            from devagent.codeprism.client import CodePrismClient
            cp = CodePrismClient(str(self._project_root))
            if cp.is_indexed:
                cp.attach_session(session_id)
                cp_client = cp
        except Exception:
            pass
        self._cp_client = cp_client

        # ── Security gate confirm callback ────────────────────────────
        def _confirm(msg: str) -> bool:
            self._console.print(f"\n[yellow]{msg}[/yellow]")
            return Confirm.ask("Proceed with write?", default=False)

        # ── Tool registry ─────────────────────────────────────────────
        gh_token = cfg.github.token or None
        registry = build_registry(
            project_root=str(self._project_root),
            codeprism_client=cp_client,
            security_log=self.security_log,
            confirm_fn=_confirm if cp_client else None,
            github_token=gh_token,
        )

        # ── Multi-model router (optional) ─────────────────────────────
        router = None
        try:
            from devagent.core.router import MultiModelRouter
            router = MultiModelRouter(cfg)
        except Exception:
            pass

        # ── Budget, memory, prompt, loop ─────────────────────────────
        budget = TokenBudget(
            max_tokens=max_tokens,
            warn_at_percent=cfg.budget.warn_at_percent,
        )
        self._budget = budget
        memory = MemoryBlock(session_id)
        self._memory = memory

        # Memory tools — agent can explicitly store/recall facts across turns
        from devagent.tools.memory_tools import register_memory_tools
        register_memory_tools(registry, memory)

        system_prompt = build_system_prompt(
            project_description=f"Project: {self._project_root.name}",
            extra_context=extra_system,
        )

        llm = LLMClient(cfg.llm)
        self._loop = AgentLoop(
            llm=llm,
            registry=registry,
            session_mgr=mgr,
            session_id=session_id,
            memory=memory,
            budget=budget,
            system_prompt=system_prompt,
            codeprism_client=cp_client,
            router=router,
        )

        # Status flags for the REPL
        self._cp_active = cp_client is not None
        self._gh_active = bool(gh_token)
        self._router_active = router is not None
        self._title_set = resume_id is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_message(self, message: str, quiet: bool = False) -> str:
        """Drive one user turn; render events. Returns the final LLM text.

        quiet=True suppresses all terminal output (used by background watcher).
        """
        from devagent.agent.loop import FinalAnswerEvent
        from devagent.output.streaming import render_events

        if quiet:
            final = ""
            for event in self._loop.run(message):
                if isinstance(event, FinalAnswerEvent):
                    final = event.text
            return final

        return render_events(self._loop.run(message))

    def interactive_repl(self, *, first_message: str | None = None) -> None:
        """Run the interactive REPL, optionally seeding with first_message."""
        if first_message:
            self.run_message(first_message)
            self._title_set = True  # seeded message serves as title

        while True:
            try:
                raw = self._console.input("[bold cyan]>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[dim]Session ended.[/dim]")
                self._print_exit()
                break

            if not raw:
                continue

            cmd = raw.lower()

            if cmd in ("/exit", "/quit", "exit", "quit"):
                self._console.print("[dim]Session ended.[/dim]")
                self._print_exit()
                break

            if cmd == "/memory":
                mem = self._memory.all()
                if mem:
                    for k, v in mem.items():
                        self._console.print(f"  [bold]{k}[/bold]: {v}")
                else:
                    self._console.print("[dim]No memory items.[/dim]")
                continue

            if cmd == "/tokens":
                self._console.print(f"  [dim]{self._budget.status_line()}[/dim]")
                for row in self._budget.per_model_summary():
                    self._console.print(
                        f"    {row['provider']}/{row['model']}: "
                        f"{row['input_tokens']:,}in / {row['output_tokens']:,}out  "
                        f"${row['cost_usd']:.4f}  ({row['calls']} calls)"
                    )
                continue

            if cmd == "/security":
                from devagent.tools.security_gate import format_security_report
                self._console.print(
                    Panel(
                        format_security_report(self.security_log),
                        title="Security Gate",
                        border_style="yellow",
                    )
                )
                continue

            if not self._title_set:
                self._mgr.set_title(self.session_id, raw[:60])
                self._title_set = True

            self.run_message(raw)

    def print_header(self, title: str = "DevAgent") -> None:
        graph = "active" if self._cp_active else "not indexed"
        gh = "active" if self._gh_active else "no token"
        router = "active" if self._router_active else "off"
        mode = "local (offline)" if self._cfg.llm.provider == "ollama" else f"cloud ({self._cfg.llm.provider})"
        self._console.print(
            Panel(
                f"[bold cyan]{title}[/bold cyan]  |  "
                f"{self._cfg.llm.provider}/{self._cfg.llm.model}  |  mode: {mode}\n"
                f"[dim]Project: {self._project_root}[/dim]\n"
                f"[dim]Graph: {graph}  |  GitHub: {gh}  |  Router: {router}[/dim]\n"
                "[dim]Commands: /memory  /tokens  /security  /exit[/dim]",
                border_style="cyan",
            )
        )

    def _print_exit(self) -> None:
        self._console.print(f"[dim]{self._budget.status_line()}[/dim]")
        if self.security_log:
            from devagent.tools.security_gate import format_security_report
            self._console.print(
                Panel(
                    format_security_report(self.security_log),
                    title="Security Gate Report",
                    border_style="yellow",
                )
            )


# ---------------------------------------------------------------------------
# Pre-fetch helpers (direct httpx, before the agent starts)
# ---------------------------------------------------------------------------

def _require_gh_token(cfg) -> str:
    token = cfg.github.token
    if not token:
        raise RuntimeError(
            "GitHub token not configured. Run: devagent init"
        )
    return token


def _slug(text: str, max_len: int = 40) -> str:
    """Convert text to a branch-name-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


# ---------------------------------------------------------------------------
# implement flow
# ---------------------------------------------------------------------------

_IMPLEMENT_SYSTEM = """\
## Flow: Implement GitHub Issue

You are implementing a specific GitHub issue end-to-end. Follow this workflow:

1. **Understand**: Read the issue. Use cp_get_file_map and cp_search_symbol to find relevant code.
2. **Branch**: Create a feature branch with git_branch_create (name: feat/issue-{number}-{slug}).
3. **Implement**: Edit the relevant files. Prefer edit_file over write_file for targeted changes.
4. **Test**: Run the test suite with run_shell after each significant change.
5. **Commit**: `run_shell("git add -A && git commit -m 'feat: <description>'")`
6. **Push**: `run_shell("git push -u origin feat/issue-{number}-{slug}")`
7. **PR**: Call gh_create_pr with body including "Closes #{number}" to link the issue.

Be explicit about every file you change and why. If tests fail, fix them before creating the PR.
"""


def run_implement(cfg, project_root: Path, issue_url: str, max_tokens: int | None = None) -> None:
    """Fetch a GitHub issue and run the implement flow."""
    console = Console()
    token = _require_gh_token(cfg)

    parsed = _parse_issue_or_pr_url(issue_url)
    if parsed.kind == "pull":
        raise ValueError("URL points to a PR, not an issue. Use 'devagent review' for PR review.")

    from devagent.tools.github_tools import GitHubAPI
    gh = GitHubAPI(token)

    repo_str = f"{parsed.owner}/{parsed.repo}"

    with console.status(f"[cyan]Fetching issue #{parsed.number} from {repo_str}...[/cyan]"):
        try:
            issue = gh.get(f"/repos/{parsed.owner}/{parsed.repo}/issues/{parsed.number}")
        except Exception as exc:
            raise RuntimeError(f"Could not fetch issue: {exc}") from exc

    title = issue.get("title", "(no title)")
    body = issue.get("body") or "(no body)"
    labels = ", ".join(l["name"] for l in issue.get("labels", []))
    branch_name = f"feat/issue-{parsed.number}-{_slug(title)}"
    extra_system = _IMPLEMENT_SYSTEM.replace("{number}", str(parsed.number)).replace("{slug}", _slug(title))

    console.print()
    console.print(
        Panel(
            f"[bold]#{parsed.number}: {title}[/bold]\n"
            f"[dim]Labels: {labels or 'none'}  |  Repo: {repo_str}[/dim]\n"
            f"[dim]Suggested branch: {branch_name}[/dim]",
            title="Implementing GitHub Issue",
            border_style="green",
        )
    )

    first_message = (
        f"Implement GitHub issue #{parsed.number} in {repo_str}.\n\n"
        f"**Title:** {title}\n\n"
        f"**Body:**\n{body}\n\n"
        f"Suggested branch name: `{branch_name}`\n"
        "Start by exploring the codebase structure, then proceed with the implementation."
    )

    session = DevAgentSession(
        cfg,
        project_root,
        max_tokens=max_tokens,
        extra_system=extra_system,
    )
    session._mgr.set_title(session.session_id, f"impl: #{parsed.number} {title[:40]}")
    session._title_set = True
    session.print_header(f"Implement: #{parsed.number} — {title[:50]}")
    session.interactive_repl(first_message=first_message)


# ---------------------------------------------------------------------------
# review flow
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM = """\
## Flow: Review Pull Request

You are reviewing a GitHub pull request. Your goal is to provide high-quality, actionable feedback.

Workflow:
1. Read the PR diff (provided in your first message)
2. For each changed file, use cp_get_impact to understand the blast radius of the change
3. Check for: bugs, missing error handling, security issues, naming/style problems, missing tests
4. Use gh_review_pr to post your review with precise inline comments (file + line + specific issue)
5. Set event=APPROVE if the code is solid, REQUEST_CHANGES if it needs work, COMMENT for observations

Be constructive and specific. Quote the relevant code in your inline comments. Suggest concrete fixes.
"""


def run_review(cfg, project_root: Path, pr_url: str, max_tokens: int | None = None) -> None:
    """Fetch a PR diff and run the code-review flow."""
    console = Console()
    token = _require_gh_token(cfg)

    parsed = _parse_issue_or_pr_url(pr_url)
    repo_str = f"{parsed.owner}/{parsed.repo}"

    from devagent.tools.github_tools import GitHubAPI
    gh = GitHubAPI(token)

    with console.status(f"[cyan]Fetching PR #{parsed.number} from {repo_str}...[/cyan]"):
        try:
            pr = gh.get(f"/repos/{parsed.owner}/{parsed.repo}/pulls/{parsed.number}")
            files = gh.get(f"/repos/{parsed.owner}/{parsed.repo}/pulls/{parsed.number}/files")
        except Exception as exc:
            raise RuntimeError(f"Could not fetch PR: {exc}") from exc

    title = pr.get("title", "(no title)")
    pr_body = pr.get("body") or "(no description)"
    head_sha = pr["head"]["sha"]
    base_branch = pr["base"]["ref"]
    head_branch = pr["head"]["ref"]

    # Build a compact diff summary for the first message
    diff_lines: list[str] = []
    total_add = total_del = 0
    for f in files[:30]:
        total_add += f.get("additions", 0)
        total_del += f.get("deletions", 0)
        diff_lines.append(
            f"[{f['status'].upper()}] {f['filename']}  "
            f"+{f.get('additions',0)} -{f.get('deletions',0)}"
        )
        patch = f.get("patch", "")
        if patch:
            patch_head = "\n".join(patch.splitlines()[:30])
            diff_lines.append(patch_head)
        diff_lines.append("")
    if len(files) > 30:
        diff_lines.append(f"... and {len(files) - 30} more files")

    console.print()
    console.print(
        Panel(
            f"[bold]PR #{parsed.number}: {title}[/bold]\n"
            f"[dim]{head_branch} → {base_branch}  |  "
            f"+{total_add} -{total_del}  |  {len(files)} files[/dim]",
            title="Reviewing Pull Request",
            border_style="blue",
        )
    )

    first_message = (
        f"Review PR #{parsed.number} in {repo_str}.\n\n"
        f"**Title:** {title}\n"
        f"**Branch:** {head_branch} → {base_branch}\n"
        f"**Head SHA:** {head_sha}\n\n"
        f"**PR Description:**\n{pr_body}\n\n"
        f"**Diff ({len(files)} files, +{total_add} -{total_del}):**\n"
        + "\n".join(diff_lines)
        + "\n\nUse cp_get_impact to assess the blast radius of each change, then submit your review."
    )

    session = DevAgentSession(
        cfg,
        project_root,
        max_tokens=max_tokens,
        extra_system=_REVIEW_SYSTEM,
    )
    session._mgr.set_title(session.session_id, f"review: PR #{parsed.number} {title[:40]}")
    session._title_set = True
    session.print_header(f"Review: PR #{parsed.number} — {title[:50]}")
    session.interactive_repl(first_message=first_message)


# ---------------------------------------------------------------------------
# triage flow
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = """\
## Flow: Triage Open Issues

You are triaging a repository's open issues. For EVERY issue:

1. Read the issue title and body carefully
2. Classify the effort: **trivial** (<1h) | **small** (1-4h) | **medium** (1-2d) | **large** (>2d) | **unclear** (needs more info)
3. Suggest appropriate labels (e.g. bug, enhancement, documentation, good-first-issue, help-wanted)
4. Use gh_comment_issue to post a triage comment with:
   - Effort estimate and rationale
   - Suggested labels
   - Clarifying questions if needed (for "unclear" issues)
5. Move to the next issue

Work systematically. Post one comment per issue. Do not skip issues.
"""


def run_triage(cfg, project_root: Path, repo: str, max_tokens: int | None = None) -> None:
    """Fetch open issues and run the triage flow."""
    console = Console()
    token = _require_gh_token(cfg)

    owner, repo_name = _parse_repo(repo)
    repo_str = f"{owner}/{repo_name}"

    from devagent.tools.github_tools import GitHubAPI
    gh = GitHubAPI(token)

    with console.status(f"[cyan]Fetching open issues for {repo_str}...[/cyan]"):
        try:
            issues = gh.get(f"/repos/{owner}/{repo_name}/issues", state="open", per_page=50)
        except Exception as exc:
            raise RuntimeError(f"Could not fetch issues: {exc}") from exc

    issues = [i for i in issues if "pull_request" not in i]
    if not issues:
        console.print(f"[yellow]No open issues found for {repo_str}.[/yellow]")
        return

    issue_list = "\n".join(
        f"  #{i['number']}  {i['title']}  "
        f"[{', '.join(l['name'] for l in i.get('labels', [])) or 'no labels'}]"
        for i in issues
    )

    console.print()
    console.print(
        Panel(
            f"[bold]{len(issues)} open issues in {repo_str}[/bold]",
            title="Triaging Issues",
            border_style="magenta",
        )
    )

    first_message = (
        f"Triage the following {len(issues)} open issues in {repo_str}.\n\n"
        f"{issue_list}\n\n"
        f"For each issue above, use gh_get_issue to read the full body, "
        f"then post a triage comment with your effort estimate and label suggestions."
    )

    session = DevAgentSession(
        cfg,
        project_root,
        max_tokens=max_tokens,
        extra_system=_TRIAGE_SYSTEM,
    )
    session._mgr.set_title(session.session_id, f"triage: {repo_str} ({len(issues)} issues)")
    session._title_set = True
    session.print_header(f"Triage: {repo_str}")
    session.interactive_repl(first_message=first_message)


# ---------------------------------------------------------------------------
# fix-ci flow
# ---------------------------------------------------------------------------

_FIX_CI_SYSTEM = """\
## Flow: Fix CI Failure

You are fixing a GitHub Actions CI failure. Workflow:

1. The failure logs are in your first message — identify the root cause
2. Use grep and cp_search_symbol to locate the failing code
3. Read the relevant files to understand the context
4. Make targeted, minimal fixes
5. Verify by running the specific failing test locally: run_shell("pytest path/to/test -x -v")
6. Once fixed, commit and push the fix
7. Optionally comment on the failed run's PR if there is one

Focus on the specific error. Avoid sweeping refactors unless the root cause requires it.
"""


def run_fix_ci(cfg, project_root: Path, run_url: str, max_tokens: int | None = None) -> None:
    """Fetch a failed CI run's logs and run the fix-ci flow."""
    console = Console()
    token = _require_gh_token(cfg)

    parsed_run = _parse_run_url(run_url)
    repo_str = f"{parsed_run.owner}/{parsed_run.repo}"

    import httpx as _httpx

    from devagent.tools.github_tools import GitHubAPI

    gh = GitHubAPI(token)

    with console.status(f"[cyan]Fetching run {parsed_run.run_id} from {repo_str}...[/cyan]"):
        try:
            run_info = gh.get(f"/repos/{parsed_run.owner}/{parsed_run.repo}/actions/runs/{parsed_run.run_id}")
            jobs_data = gh.get(f"/repos/{parsed_run.owner}/{parsed_run.repo}/actions/runs/{parsed_run.run_id}/jobs")
        except Exception as exc:
            raise RuntimeError(f"Could not fetch run: {exc}") from exc

    all_jobs = jobs_data.get("jobs", [])
    failed_jobs = [j for j in all_jobs if j.get("conclusion") in ("failure", "timed_out")]
    if not failed_jobs:
        failed_jobs = [j for j in all_jobs if j.get("conclusion") not in ("success", "skipped", None)]

    run_name = run_info.get("display_title") or run_info.get("name", f"Run #{parsed_run.run_id}")
    conclusion = run_info.get("conclusion", "unknown")
    branch = run_info.get("head_branch", "")
    commit_sha = run_info.get("head_sha", "")[:7]

    log_sections: list[str] = []
    for job in failed_jobs[:3]:
        job_id = job["id"]
        bad_steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") in ("failure", "timed_out")]
        log_sections.append(f"Job: {job.get('name', '?')} — failed steps: {', '.join(bad_steps) or 'none'}")
        try:
            r = _httpx.get(
                f"https://api.github.com/repos/{parsed_run.owner}/{parsed_run.repo}/actions/jobs/{job_id}/logs",
                headers=gh._headers,
                follow_redirects=True,
                timeout=60,
            )
            if r.status_code == 200:
                tail = r.text.splitlines()[-120:]
                log_sections.append("\n".join(tail))
        except Exception:
            log_sections.append("(could not fetch log)")

    console.print()
    console.print(
        Panel(
            f"[bold]Run: {run_name}[/bold]\n"
            f"[dim]Conclusion: {conclusion}  |  Branch: {branch}  |  Commit: {commit_sha}[/dim]\n"
            f"[dim]Failed jobs: {len(failed_jobs)}[/dim]",
            title="Fix CI Failure",
            border_style="red",
        )
    )

    first_message = (
        f"Fix the CI failure in run {parsed_run.run_id} of {repo_str}.\n\n"
        f"**Run:** {run_name}\n"
        f"**Branch:** {branch}  |  **Commit:** {commit_sha}\n\n"
        f"**Failed job logs:**\n"
        + "\n\n---\n\n".join(log_sections)
        + "\n\nIdentify the root cause, locate the failing code, and implement a fix."
    )

    session = DevAgentSession(
        cfg,
        project_root,
        max_tokens=max_tokens,
        extra_system=_FIX_CI_SYSTEM,
    )
    session._mgr.set_title(session.session_id, f"fix-ci: run {parsed_run.run_id} ({repo_str})")
    session._title_set = True
    session.print_header(f"Fix CI: {run_name[:50]}")
    session.interactive_repl(first_message=first_message)
