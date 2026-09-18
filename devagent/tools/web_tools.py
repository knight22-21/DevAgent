"""Phase 11 — Web tools: web_search and fetch_url.

web_search: dispatches to Brave Search API or a SearXNG-compatible SearchX
instance based on configuration.  Only registered when at least one API key
(brave or searchx) is configured.

fetch_url: always registered — no API key required.  Fetches any URL with
httpx and optionally strips HTML tags to plain text.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

_DEFAULT_UA = "DevAgent/0.5 (https://github.com/knight22-21/DevAgent)"
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_MAX_FETCH_CHARS = 8_000   # cap fetch_url text output
_SKIP_TAGS = frozenset({"script", "style", "head", "noscript", "nav", "footer"})
_BLOCK_TAGS = frozenset({"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr", "dt", "dd"})


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tl = tag.lower()
        if tl in _SKIP_TAGS:
            self._skip_depth += 1
        elif tl in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)


def _html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    text = "".join(extractor._parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()[:_MAX_FETCH_CHARS]


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _search_brave(query: str, num_results: int, api_key: str) -> str:
    import httpx

    try:
        resp = httpx.get(
            _BRAVE_SEARCH_URL,
            params={"q": query, "count": min(num_results, 20)},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return f"[error] Brave Search returned {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        return f"[error] Brave Search failed: {exc}"

    results = resp.json().get("web", {}).get("results", [])
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results[:num_results], 1):
        lines.append(
            f"{i}. {r.get('title', '')}\n"
            f"   {r.get('url', '')}\n"
            f"   {r.get('description', '')}"
        )
    return "\n\n".join(lines)


def _search_searchx(
    query: str,
    num_results: int,
    base_url: str,
    api_key: str,
) -> str:
    import httpx

    headers: dict[str, str] = {"User-Agent": _DEFAULT_UA}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = httpx.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "pageno": 1},
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return f"[error] SearchX returned {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        return f"[error] SearchX failed: {exc}"

    results = resp.json().get("results", [])
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results[:num_results], 1):
        lines.append(
            f"{i}. {r.get('title', '')}\n"
            f"   {r.get('url', '')}\n"
            f"   {r.get('content', '')}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_web_tools(
    registry,
    brave_api_key: str = "",
    searchx_api_key: str = "",
    searchx_base_url: str = "http://localhost:8888",
    search_provider: str = "searchx",
) -> None:
    """Register fetch_url (always) and web_search (when a key is configured)."""

    # ── fetch_url ─────────────────────────────────────────────────────────

    def fetch_url(args: dict[str, Any]) -> str:
        url = args.get("url", "").strip()
        if not url:
            return "[error] url is required"
        extract_text = args.get("extract_text", True)
        try:
            import httpx
            resp = httpx.get(
                url,
                headers={"User-Agent": _DEFAULT_UA},
                timeout=20.0,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:
            return f"[error] fetch failed: {exc}"

        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type and extract_text:
            return _html_to_text(resp.text)
        return resp.text[:_MAX_FETCH_CHARS]

    registry.register(
        "fetch_url",
        (
            "Fetch the content of a URL and return it as text. "
            "For HTML pages, strips tags to return readable plain text. "
            "Use this to read documentation, inspect web APIs, or retrieve any URL."
        ),
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "extract_text": {
                    "type": "boolean",
                    "description": "Strip HTML tags and return plain text (default true)",
                },
            },
            "required": ["url"],
        },
        fetch_url,
    )

    # ── web_search ─────────────────────────────────────────────────────────

    has_brave = bool(brave_api_key)
    has_searchx = bool(searchx_api_key) or search_provider == "searchx"
    active_provider = search_provider if (has_brave or has_searchx) else None

    # Only register web_search when at least Brave is configured, or SearchX
    # base URL is available (SearchX can run without an api_key locally)
    if not (brave_api_key or searchx_base_url):
        return

    def web_search(args: dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "[error] query is required"
        num = min(int(args.get("num_results", 5)), 20)
        provider = args.get("provider", active_provider or search_provider)

        if provider == "brave":
            if not brave_api_key:
                return "[error] Brave API key not configured — set cfg.brave.api_key"
            return _search_brave(query, num, brave_api_key)
        else:
            return _search_searchx(query, num, searchx_base_url, searchx_api_key)

    registry.register(
        "web_search",
        (
            "Search the web for information. Returns titles, URLs, and snippets. "
            f"Configured provider: {search_provider}. "
            "Use this to look up documentation, find packages, or research any topic."
        ),
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 20)",
                },
                "provider": {
                    "type": "string",
                    "description": "Override provider: 'brave' or 'searchx'",
                    "enum": ["brave", "searchx"],
                },
            },
            "required": ["query"],
        },
        web_search,
    )
