from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse


class InvalidGitHubURLError(Exception):
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Cannot parse GitHub URL '{url}': {reason}")

@dataclass
class ParsedGitHubURL:
    owner: str                          # e.g. "myorg"
    repo: str                           # e.g. "backend"
    number: int                         # issue or PR number
    resource_type: Literal["issue", "pull_request"]
    raw_url: str                        # the original URL as provided

def parse_github_url(url: str) -> ParsedGitHubURL:
    if not url.startswith("http"):
        url = "https://" + url

    parsed = urlparse(url)
    
    if parsed.netloc != "github.com":
        raise InvalidGitHubURLError(url, "Not a github.com URL")

    # Split path and remove empty strings
    parts = [p for p in parsed.path.split("/") if p]

    if len(parts) != 4:
        raise InvalidGitHubURLError(url, "Invalid path structure. Use the full GitHub URL")

    owner = parts[0]
    repo = parts[1]
    resource_type_str = parts[2]
    number_str = parts[3]

    if resource_type_str not in ("issues", "pull"):
        raise InvalidGitHubURLError(url, "URL must point to an issue or pull request")

    try:
        number = int(number_str)
    except ValueError:
        raise InvalidGitHubURLError(url, "Issue or PR number must be an integer")

    resource_type: Literal["issue", "pull_request"] = "issue" if resource_type_str == "issues" else "pull_request"

    return ParsedGitHubURL(owner, repo, number, resource_type, url)

def format_repo_string(parsed: ParsedGitHubURL) -> str:
    return f"{parsed.owner}/{parsed.repo}"
