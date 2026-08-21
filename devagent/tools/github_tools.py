"""GitHub API tools for the agent tool registry.

All tools call the GitHub REST API v3 with a personal access token.
Requires the 'repo' and 'workflow' OAuth scopes for full functionality.

Tool taxonomy:
  gh_get_issue          — fetch issue / PR body, labels, metadata
  gh_list_issues        — list open issues (triage)
  gh_create_pr          — create a pull request
  gh_list_pr_files      — list changed files + diff in a PR
  gh_review_pr          — submit a PR review with optional inline comments
  gh_comment_issue      — post a comment on an issue or PR
  gh_branch_create      — create a branch ref via API
  gh_list_workflow_runs — list recent CI workflow runs
  gh_get_run_logs       — fetch logs from a failed CI run
"""

from __future__ import annotations

from typing import Any

import httpx

from devagent.tools.registry import ToolRegistry

_BASE = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VER = "2022-11-28"


# ---------------------------------------------------------------------------
# GitHubAPI — thin synchronous client, importable by flows.py too
# ---------------------------------------------------------------------------

class GitHubAPI:
    """Minimal synchronous GitHub REST API client."""

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VER,
        }

    def get(self, path: str, **params) -> Any:
        r = httpx.get(
            f"{_BASE}{path}",
            headers=self._headers,
            params={k: v for k, v in params.items() if v is not None},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> Any:
        r = httpx.post(
            f"{_BASE}{path}",
            headers=self._headers,
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def text(self, path: str, *, follow_redirects: bool = True, timeout: int = 60) -> str:
        r = httpx.get(
            f"{_BASE}{path}",
            headers=self._headers,
            follow_redirects=follow_redirects,
            timeout=timeout,
        )
        r.raise_for_status()
        return r.text


def _split_repo(repo: str) -> tuple[str, str]:
    parts = repo.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"repo must be 'owner/repo', got: {repo!r}")
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_github_tools(registry: ToolRegistry, token: str) -> None:
    """Register all gh_* tools using the provided GitHub personal access token."""
    gh = GitHubAPI(token)

    # ------------------------------------------------------------------
    # gh_get_issue
    # ------------------------------------------------------------------
    def gh_get_issue(args: dict) -> str:
        repo = args.get("repo", "")
        number = args.get("number")
        if not repo or number is None:
            return "[error] repo and number are required"
        try:
            owner, repo_name = _split_repo(repo)
            d = gh.get(f"/repos/{owner}/{repo_name}/issues/{number}")
            labels = ", ".join(l["name"] for l in d.get("labels", []))
            assignees = ", ".join(a["login"] for a in d.get("assignees", []))
            pr_note = ""
            if "pull_request" in d:
                pr_note = f"\nPR URL: {d['pull_request'].get('html_url', '')}"
            return (
                f"Issue #{d['number']}: {d['title']}\n"
                f"State: {d['state']}\n"
                f"Labels: {labels or 'none'}\n"
                f"Assignees: {assignees or 'none'}\n"
                f"Author: {d['user']['login']}\n"
                f"URL: {d['html_url']}{pr_note}\n\n"
                f"Body:\n{d.get('body') or '(no body)'}"
            )
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_get_issue",
        "Fetch a GitHub issue or PR by number. Returns title, body, labels, assignees, state.",
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo"},
                "number": {"type": "integer", "description": "Issue or PR number"},
            },
            "required": ["repo", "number"],
        },
        gh_get_issue,
    )

    # ------------------------------------------------------------------
    # gh_list_issues
    # ------------------------------------------------------------------
    def gh_list_issues(args: dict) -> str:
        repo = args.get("repo", "")
        state = args.get("state", "open")
        labels = args.get("labels")
        limit = min(int(args.get("limit", 30)), 100)
        if not repo:
            return "[error] repo is required"
        try:
            owner, repo_name = _split_repo(repo)
            kwargs = {"state": state, "per_page": limit}
            if labels:
                kwargs["labels"] = labels
            data = gh.get(f"/repos/{owner}/{repo_name}/issues", **kwargs)
            issues = [i for i in data if "pull_request" not in i]
            if not issues:
                return f"No {state} issues found in {repo}."
            lines = [f"{len(issues)} {state} issue(s) in {repo}:"]
            for i in issues:
                label_str = ", ".join(l["name"] for l in i.get("labels", []))
                lines.append(
                    f"  #{i['number']}  {i['title']}"
                    + (f"  [{label_str}]" if label_str else "")
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_list_issues",
        "List open (or closed) issues for a repository. Useful for triage workflows.",
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                "labels": {"type": "string", "description": "Comma-separated label filter"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": ["repo"],
        },
        gh_list_issues,
    )

    # ------------------------------------------------------------------
    # gh_create_pr
    # ------------------------------------------------------------------
    def gh_create_pr(args: dict) -> str:
        repo = args.get("repo", "")
        title = args.get("title", "")
        body = args.get("body", "")
        head = args.get("head", "")
        base = args.get("base", "main")
        draft = bool(args.get("draft", False))
        if not repo or not title or not head:
            return "[error] repo, title, and head are required"
        try:
            owner, repo_name = _split_repo(repo)
            d = gh.post(f"/repos/{owner}/{repo_name}/pulls", {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
            })
            return (
                f"PR #{d['number']} created: {d['html_url']}\n"
                f"Title: {d['title']}\n"
                f"Branch: {d['head']['ref']} → {d['base']['ref']}\n"
                f"State: {'draft' if d.get('draft') else d['state']}"
            )
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_create_pr",
        (
            "Create a GitHub pull request. "
            "head is the source branch (e.g. feat/my-branch), base is the target (default: main). "
            "The head branch must already be pushed to GitHub before calling this."
        ),
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string", "description": "PR description (markdown). Include 'Closes #N' to link the issue."},
                "head": {"type": "string", "description": "Source branch name"},
                "base": {"type": "string", "default": "main"},
                "draft": {"type": "boolean", "default": False},
            },
            "required": ["repo", "title", "head"],
        },
        gh_create_pr,
    )

    # ------------------------------------------------------------------
    # gh_list_pr_files
    # ------------------------------------------------------------------
    def gh_list_pr_files(args: dict) -> str:
        repo = args.get("repo", "")
        number = args.get("number")
        if not repo or number is None:
            return "[error] repo and number are required"
        try:
            owner, repo_name = _split_repo(repo)
            files = gh.get(f"/repos/{owner}/{repo_name}/pulls/{number}/files")
            lines = [f"Files changed in PR #{number} ({len(files)} file(s)):"]
            for f in files:
                lines.append(
                    f"\n[{f['status'].upper()}] {f['filename']}"
                    f"  +{f.get('additions', 0)} -{f.get('deletions', 0)}"
                )
                patch = f.get("patch", "")
                if patch:
                    patch_lines = patch.splitlines()
                    shown = patch_lines[:50]
                    lines.append("\n".join(f"  {l}" for l in shown))
                    if len(patch_lines) > 50:
                        lines.append(f"  ... ({len(patch_lines) - 50} more patch lines)")
            return "\n".join(lines)
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_list_pr_files",
        "List all files changed in a pull request, with their diffs.",
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
            },
            "required": ["repo", "number"],
        },
        gh_list_pr_files,
    )

    # ------------------------------------------------------------------
    # gh_review_pr
    # ------------------------------------------------------------------
    def gh_review_pr(args: dict) -> str:
        repo = args.get("repo", "")
        number = args.get("number")
        body = args.get("body", "")
        comments = args.get("comments") or []
        event = args.get("event", "COMMENT").upper()
        if not repo or number is None:
            return "[error] repo and number are required"
        if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
            return "[error] event must be APPROVE, REQUEST_CHANGES, or COMMENT"
        try:
            owner, repo_name = _split_repo(repo)
            pr = gh.get(f"/repos/{owner}/{repo_name}/pulls/{number}")
            commit_id = pr["head"]["sha"]

            gh_comments = []
            for c in comments:
                entry = {"path": c["path"], "body": c["body"]}
                if "line" in c:
                    entry["line"] = c["line"]
                    entry["side"] = c.get("side", "RIGHT")
                elif "position" in c:
                    entry["position"] = c["position"]
                gh_comments.append(entry)

            payload: dict = {"commit_id": commit_id, "body": body, "event": event}
            if gh_comments:
                payload["comments"] = gh_comments

            d = gh.post(f"/repos/{owner}/{repo_name}/pulls/{number}/reviews", payload)
            return (
                f"Review submitted on PR #{number}: {event}\n"
                f"Review ID: {d.get('id')}  |  Inline comments: {len(gh_comments)}"
            )
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_review_pr",
        (
            "Submit a GitHub PR review. event: APPROVE | REQUEST_CHANGES | COMMENT. "
            "Optional inline comments: [{path, line, body}, ...]. "
            "The current head SHA is fetched automatically."
        ),
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
                "body": {"type": "string", "description": "Overall review summary (markdown)"},
                "event": {
                    "type": "string",
                    "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    "default": "COMMENT",
                },
                "comments": {
                    "type": "array",
                    "description": "Inline comments. Each: {path, line, body}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                            "body": {"type": "string"},
                        },
                        "required": ["path", "body"],
                    },
                },
            },
            "required": ["repo", "number"],
        },
        gh_review_pr,
    )

    # ------------------------------------------------------------------
    # gh_comment_issue
    # ------------------------------------------------------------------
    def gh_comment_issue(args: dict) -> str:
        repo = args.get("repo", "")
        number = args.get("number")
        body = args.get("body", "")
        if not repo or number is None or not body:
            return "[error] repo, number, and body are required"
        try:
            owner, repo_name = _split_repo(repo)
            d = gh.post(f"/repos/{owner}/{repo_name}/issues/{number}/comments", {"body": body})
            return f"Comment posted on #{number}: {d['html_url']}"
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_comment_issue",
        "Post a comment on a GitHub issue or PR.",
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
                "body": {"type": "string"},
            },
            "required": ["repo", "number", "body"],
        },
        gh_comment_issue,
    )

    # ------------------------------------------------------------------
    # gh_branch_create
    # ------------------------------------------------------------------
    def gh_branch_create(args: dict) -> str:
        repo = args.get("repo", "")
        branch = args.get("branch", "")
        sha = args.get("sha", "")
        if not repo or not branch or not sha:
            return "[error] repo, branch, and sha are required"
        try:
            owner, repo_name = _split_repo(repo)
            d = gh.post(f"/repos/{owner}/{repo_name}/git/refs", {
                "ref": f"refs/heads/{branch}",
                "sha": sha,
            })
            return f"Branch '{branch}' created at {sha[:7]} on GitHub."
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_branch_create",
        (
            "Create a branch on GitHub via API. sha must be the full or 7-char commit SHA. "
            "Use git_log to get the current HEAD SHA, then push it here."
        ),
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "branch": {"type": "string", "description": "New branch name"},
                "sha": {"type": "string", "description": "Base commit SHA"},
            },
            "required": ["repo", "branch", "sha"],
        },
        gh_branch_create,
    )

    # ------------------------------------------------------------------
    # gh_list_workflow_runs
    # ------------------------------------------------------------------
    def gh_list_workflow_runs(args: dict) -> str:
        repo = args.get("repo", "")
        branch = args.get("branch")
        status = args.get("status")
        limit = min(int(args.get("limit", 10)), 50)
        if not repo:
            return "[error] repo is required"
        try:
            owner, repo_name = _split_repo(repo)
            kwargs: dict = {"per_page": limit}
            if branch:
                kwargs["branch"] = branch
            if status:
                kwargs["status"] = status
            d = gh.get(f"/repos/{owner}/{repo_name}/actions/runs", **kwargs)
            runs = d.get("workflow_runs", [])
            if not runs:
                return f"No workflow runs found for {repo}."
            lines = [f"Workflow runs for {repo} ({len(runs)} returned):"]
            for r in runs:
                conclusion = r.get("conclusion") or r["status"]
                lines.append(
                    f"  Run #{r['run_number']} [{conclusion}]  "
                    f"{r.get('display_title') or r.get('name', '?')[:60]}  "
                    f"({(r.get('created_at') or '')[:10]})  id={r['id']}"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_list_workflow_runs",
        "List recent GitHub Actions workflow runs for a repository.",
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "branch": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["queued", "in_progress", "completed"],
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["repo"],
        },
        gh_list_workflow_runs,
    )

    # ------------------------------------------------------------------
    # gh_get_run_logs
    # ------------------------------------------------------------------
    def gh_get_run_logs(args: dict) -> str:
        repo = args.get("repo", "")
        run_id = str(args.get("run_id", ""))
        if not repo or not run_id:
            return "[error] repo and run_id are required"
        try:
            owner, repo_name = _split_repo(repo)

            # Fetch jobs for this run
            jobs_data = gh.get(f"/repos/{owner}/{repo_name}/actions/runs/{run_id}/jobs")
            all_jobs = jobs_data.get("jobs", [])

            # Prefer failed jobs; fall back to all non-success
            failed_jobs = [j for j in all_jobs if j.get("conclusion") in ("failure", "timed_out")]
            if not failed_jobs:
                failed_jobs = [j for j in all_jobs if j.get("conclusion") not in ("success", "skipped", None)]
            if not failed_jobs:
                conclusions = {j.get("conclusion") for j in all_jobs}
                return f"No failed jobs in run {run_id}. Job conclusions: {conclusions}"

            result: list[str] = [f"Failed CI run {run_id} ({repo}):"]
            for job in failed_jobs[:3]:
                job_id = job["id"]
                job_name = job.get("name", "?")
                steps = job.get("steps", [])
                bad_steps = [s["name"] for s in steps if s.get("conclusion") in ("failure", "timed_out")]

                result.append(f"\nJob: {job_name}  (id={job_id})")
                if bad_steps:
                    result.append(f"  Failed steps: {', '.join(bad_steps)}")

                try:
                    r = httpx.get(
                        f"{_BASE}/repos/{owner}/{repo_name}/actions/jobs/{job_id}/logs",
                        headers=gh._headers,
                        follow_redirects=True,
                        timeout=60,
                    )
                    if r.status_code == 200:
                        lines = r.text.splitlines()
                        tail = lines[-150:] if len(lines) > 150 else lines
                        result.append(f"  Log tail ({len(tail)} lines):")
                        result.extend(f"    {l}" for l in tail)
                    else:
                        result.append(f"  [log fetch: HTTP {r.status_code}]")
                except Exception as e:
                    result.append(f"  [log fetch error: {e}]")

            return "\n".join(result)
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "gh_get_run_logs",
        "Get logs from a failed GitHub Actions workflow run. Returns the tail of each failed job log.",
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "run_id": {"type": "string", "description": "Workflow run ID (from gh_list_workflow_runs)"},
            },
            "required": ["repo", "run_id"],
        },
        gh_get_run_logs,
    )
