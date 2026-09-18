"""Tests for GitHub tools and flow URL parsers."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# URL parser tests
# ---------------------------------------------------------------------------

def test_parse_issue_url():
    from devagent.agent.flows import _parse_issue_or_pr_url
    p = _parse_issue_or_pr_url("https://github.com/acme/backend/issues/42")
    assert p.owner == "acme"
    assert p.repo == "backend"
    assert p.number == 42
    assert p.kind == "issues"


def test_parse_pr_url():
    from devagent.agent.flows import _parse_issue_or_pr_url
    p = _parse_issue_or_pr_url("https://github.com/acme/backend/pull/7")
    assert p.number == 7
    assert p.kind == "pull"


def test_parse_issue_url_invalid():
    from devagent.agent.flows import _parse_issue_or_pr_url
    with pytest.raises(ValueError, match="Cannot parse"):
        _parse_issue_or_pr_url("https://github.com/acme/backend")


def test_parse_run_url():
    from devagent.agent.flows import _parse_run_url
    r = _parse_run_url("https://github.com/acme/backend/actions/runs/987654321")
    assert r.owner == "acme"
    assert r.repo == "backend"
    assert r.run_id == "987654321"


def test_parse_run_url_invalid():
    from devagent.agent.flows import _parse_run_url
    with pytest.raises(ValueError, match="Cannot parse"):
        _parse_run_url("https://github.com/acme/backend/issues/5")


def test_parse_repo_slash():
    from devagent.agent.flows import _parse_repo
    owner, repo = _parse_repo("acme/backend")
    assert owner == "acme" and repo == "backend"


def test_parse_repo_url():
    from devagent.agent.flows import _parse_repo
    owner, repo = _parse_repo("https://github.com/acme/backend")
    assert owner == "acme" and repo == "backend"


def test_parse_repo_invalid():
    from devagent.agent.flows import _parse_repo
    with pytest.raises(ValueError):
        _parse_repo("not-a-repo")


def test_slug():
    from devagent.agent.flows import _slug
    assert _slug("Add user authentication") == "add-user-authentication"
    assert _slug("Fix bug #42!") == "fix-bug-42"
    assert len(_slug("x" * 100)) <= 40


# ---------------------------------------------------------------------------
# GitHubAPI unit tests (mocked httpx)
# ---------------------------------------------------------------------------

def _make_response(json_data=None, text_data=None, status=200):
    r = MagicMock()
    r.status_code = status
    if json_data is not None:
        r.json.return_value = json_data
    if text_data is not None:
        r.text = text_data
    r.raise_for_status = MagicMock()
    return r


@patch("devagent.tools.github_tools.httpx.get")
def test_github_api_get(mock_get):
    from devagent.tools.github_tools import GitHubAPI
    mock_get.return_value = _make_response({"number": 1, "title": "Test"})
    gh = GitHubAPI("fake-token")
    result = gh.get("/repos/acme/backend/issues/1")
    assert result["title"] == "Test"
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert "fake-token" in call_args[1]["headers"]["Authorization"]


@patch("devagent.tools.github_tools.httpx.post")
def test_github_api_post(mock_post):
    from devagent.tools.github_tools import GitHubAPI
    mock_post.return_value = _make_response({"id": 99, "html_url": "https://github.com/..."})
    gh = GitHubAPI("fake-token")
    result = gh.post("/repos/acme/backend/issues/1/comments", {"body": "hello"})
    assert result["id"] == 99


# ---------------------------------------------------------------------------
# Tool handler tests (mocked GitHubAPI)
# ---------------------------------------------------------------------------

def _make_registry_with_mocked_gh(mock_gh: MagicMock):
    """Build a registry where GitHubAPI is replaced by mock_gh."""
    from devagent.tools.github_tools import register_github_tools
    from devagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    with patch("devagent.tools.github_tools.GitHubAPI", return_value=mock_gh):
        register_github_tools(registry, "fake-token")
    return registry


def _mock_gh(get_return=None, post_return=None):
    gh = MagicMock()
    gh.get.return_value = get_return or {}
    gh.post.return_value = post_return or {}
    gh._headers = {"Authorization": "token fake"}
    return gh


def test_gh_get_issue_tool():
    gh = _mock_gh(get_return={
        "number": 42,
        "title": "Add auth",
        "state": "open",
        "labels": [{"name": "enhancement"}],
        "assignees": [],
        "user": {"login": "alice"},
        "html_url": "https://github.com/acme/backend/issues/42",
        "body": "We need auth.",
    })
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_get_issue", {"repo": "acme/backend", "number": 42})
    assert "Add auth" in result
    assert "#42" in result
    assert "We need auth." in result


def test_gh_get_issue_missing_args():
    gh = _mock_gh()
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_get_issue", {"repo": "acme/backend"})
    assert "[error]" in result


def test_gh_list_issues_tool():
    gh = _mock_gh(get_return=[
        {"number": 1, "title": "Bug 1", "labels": [{"name": "bug"}]},
        {"number": 2, "title": "Feature", "labels": [], "pull_request": {}},  # PR — should be skipped
    ])
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_list_issues", {"repo": "acme/backend"})
    assert "#1" in result
    assert "Bug 1" in result
    assert "Feature" not in result   # PRs filtered out


def test_gh_create_pr_tool():
    gh = _mock_gh(post_return={
        "number": 5,
        "html_url": "https://github.com/acme/backend/pull/5",
        "title": "Add auth",
        "head": {"ref": "feat/auth"},
        "base": {"ref": "main"},
        "state": "open",
        "draft": False,
    })
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_create_pr", {
        "repo": "acme/backend",
        "title": "Add auth",
        "head": "feat/auth",
    })
    assert "PR #5" in result
    assert "https://github.com" in result


def test_gh_create_pr_missing_head():
    gh = _mock_gh()
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_create_pr", {"repo": "acme/backend", "title": "x"})
    assert "[error]" in result


def test_gh_list_pr_files_tool():
    gh = _mock_gh(get_return=[
        {"filename": "src/auth.py", "status": "added", "additions": 50, "deletions": 0, "patch": "@@ +1 @@\n+new line"},
    ])
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_list_pr_files", {"repo": "acme/backend", "number": 5})
    assert "src/auth.py" in result
    assert "ADDED" in result


def test_gh_review_pr_tool():
    gh = _mock_gh(
        get_return={"head": {"sha": "abc123def456"}},
        post_return={"id": 999},
    )
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_review_pr", {
        "repo": "acme/backend",
        "number": 5,
        "body": "Looks good",
        "event": "APPROVE",
    })
    assert "APPROVE" in result
    assert "999" in result


def test_gh_review_pr_invalid_event():
    gh = _mock_gh()
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_review_pr", {
        "repo": "acme/backend",
        "number": 5,
        "event": "LGTM",
    })
    assert "[error]" in result


def test_gh_comment_issue_tool():
    gh = _mock_gh(post_return={"html_url": "https://github.com/.../comments/1"})
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_comment_issue", {
        "repo": "acme/backend",
        "number": 42,
        "body": "Triage: small effort",
    })
    assert "https://github.com" in result


def test_gh_comment_issue_missing_body():
    gh = _mock_gh()
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_comment_issue", {"repo": "acme/backend", "number": 1})
    assert "[error]" in result


def test_gh_branch_create_tool():
    gh = _mock_gh(post_return={"url": "https://api.github.com/repos/acme/backend/git/refs/heads/feat/x"})
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_branch_create", {
        "repo": "acme/backend",
        "branch": "feat/x",
        "sha": "abc123def456",
    })
    assert "feat/x" in result
    assert "abc123d" in result


def test_gh_list_workflow_runs_tool():
    gh = _mock_gh(get_return={"workflow_runs": [
        {
            "run_number": 42,
            "conclusion": "failure",
            "display_title": "CI build",
            "created_at": "2025-08-01T12:00:00Z",
            "id": 9876543,
            "status": "completed",
        }
    ]})
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_list_workflow_runs", {"repo": "acme/backend"})
    assert "Run #42" in result
    assert "failure" in result
    assert "9876543" in result


def test_gh_get_run_logs_no_failed_jobs():
    gh = _mock_gh(get_return={"jobs": [
        {"id": 1, "name": "build", "conclusion": "success", "steps": []}
    ]})
    registry = _make_registry_with_mocked_gh(gh)
    result = registry.call("gh_get_run_logs", {"repo": "acme/backend", "run_id": "123"})
    assert "No failed jobs" in result


def test_gh_get_run_logs_with_failed_job():
    gh = _mock_gh(get_return={"jobs": [
        {
            "id": 99,
            "name": "test",
            "conclusion": "failure",
            "steps": [{"name": "pytest", "conclusion": "failure"}],
        }
    ]})
    registry = _make_registry_with_mocked_gh(gh)

    with patch("devagent.tools.github_tools.httpx.get") as mock_get:
        mock_get.return_value = _make_response(text_data="ERROR: test failed\nassert 1 == 2", status=200)
        result = registry.call("gh_get_run_logs", {"repo": "acme/backend", "run_id": "123"})

    assert "test" in result
    assert "pytest" in result


# ---------------------------------------------------------------------------
# Registry integration — github_token wires tools
# ---------------------------------------------------------------------------

def test_registry_with_token_has_gh_tools():
    from devagent.tools.registry import build_registry
    reg = build_registry(github_token="fake-token")
    gh_tools = [n for n in reg.names() if n.startswith("gh_")]
    assert len(gh_tools) == 9


def test_registry_without_token_no_gh_tools():
    from devagent.tools.registry import build_registry
    reg = build_registry()
    assert not any(n.startswith("gh_") for n in reg.names())


def test_split_repo_valid():
    from devagent.tools.github_tools import _split_repo
    assert _split_repo("acme/backend") == ("acme", "backend")


def test_split_repo_invalid():
    from devagent.tools.github_tools import _split_repo
    with pytest.raises(ValueError):
        _split_repo("not-a-repo")
    with pytest.raises(ValueError):
        _split_repo("too/many/slashes")
