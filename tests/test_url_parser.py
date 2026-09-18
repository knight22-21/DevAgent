import pytest

from devagent.core.url_parser import InvalidGitHubURLError, format_repo_string, parse_github_url


def test_standard_issue_url():
    result = parse_github_url("https://github.com/myorg/backend/issues/142")
    assert result.owner == "myorg"
    assert result.repo == "backend"
    assert result.number == 142
    assert result.resource_type == "issue"

def test_pr_url():
    result = parse_github_url("https://github.com/myorg/backend/pull/87")
    assert result.resource_type == "pull_request"
    assert result.number == 87

def test_trailing_slash():
    result = parse_github_url("https://github.com/myorg/backend/issues/142/")
    assert result.number == 142

def test_url_with_query_params():
    result = parse_github_url("https://github.com/myorg/backend/issues/142?notification_referrer_id=abc")
    assert result.number == 142

def test_url_with_fragment():
    result = parse_github_url("https://github.com/myorg/backend/issues/142#issuecomment-123456")
    assert result.number == 142

def test_without_https():
    result = parse_github_url("github.com/myorg/backend/issues/142")
    assert result.owner == "myorg"
    assert result.number == 142

def test_non_github_url_raises():
    with pytest.raises(InvalidGitHubURLError):
        parse_github_url("https://gitlab.com/myorg/backend/issues/142")

def test_short_form_raises():
    with pytest.raises(InvalidGitHubURLError):
        parse_github_url("myorg/backend#142")

def test_invalid_number_raises():
    with pytest.raises(InvalidGitHubURLError):
        parse_github_url("https://github.com/myorg/backend/issues/abc")

def test_format_repo_string():
    parsed = parse_github_url("https://github.com/myorg/backend/issues/142")
    assert format_repo_string(parsed) == "myorg/backend"
