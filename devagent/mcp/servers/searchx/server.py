"""FastMCP server: SearchXMCP."""

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

from devagent.core.config import load_config
from devagent.core.storage import get_config_path


# Initialize FastMCP server
mcp = FastMCP("SearchXMCP")


def _get_api_key() -> str:
    """Get the SearchX API key from config or environment."""
    # Check environment variable first (set by manager.py)
    api_key = os.environ.get("SEARCHX_API_KEY")
    if api_key:
        return api_key
    
    # Fallback to loading from config
    try:
        config = load_config()
        return config.searchx.api_key
    except Exception:
        return ""


@mcp.tool()
def searchx_web_search(query: str, count: int = 10):
    """Search the web using SearchX API.

    Args:
        query: The search query string.
        count: Number of results to return (default: 10, max: 100).

    Returns:
        JSON string representing search results with title, url, snippet, and metadata.
    """
    api_key = _get_api_key()
    
    if not api_key:
        return json.dumps({
            "error": "SearchX API key not configured",
            "results": []
        })
    
    # Limit count to reasonable range
    count = min(max(1, count), 100)
    
    try:
        response = httpx.get(
            "https://searchx.dev/api/v1/search",
            params={
                "q": query,
                "count": count
            },
            headers={
                "X-API-Key": api_key,
                "Accept": "application/json"
            },
            timeout=30.0
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Normalize the response format to match typical search API structure
        # SearchX may return different field names, so we normalize them
        results = []
        
        if isinstance(data, dict):
            # SearchX might return results in different formats
            if "results" in data:
                raw_results = data["results"]
            elif "data" in data:
                raw_results = data["data"]
            elif "items" in data:
                raw_results = data["items"]
            else:
                # If the response itself is the results array
                raw_results = data if isinstance(data, list) else []
        elif isinstance(data, list):
            raw_results = data
        else:
            raw_results = []
        
        for item in raw_results:
            if not isinstance(item, dict):
                continue
                
            result = {
                "title": item.get("title") or item.get("name") or "",
                "url": item.get("url") or item.get("link") or item.get("href") or "",
                "snippet": item.get("snippet") or item.get("description") or item.get("abstract") or "",
                "published_date": item.get("published_date") or item.get("date") or None,
                "source": item.get("source") or item.get("domain") or ""
            }
            
            # Only include results with at least a URL
            if result["url"]:
                results.append(result)
        
        return json.dumps({
            "query": query,
            "results": results,
            "total": len(results)
        })
        
    except httpx.HTTPStatusError as e:
        return json.dumps({
            "error": f"HTTP error: {e.response.status_code}",
            "message": str(e),
            "results": []
        })
    except httpx.TimeoutException:
        return json.dumps({
            "error": "Request timeout",
            "results": []
        })
    except Exception as e:
        return json.dumps({
            "error": f"Search failed: {str(e)}",
            "results": []
        })


if __name__ == "__main__":
    mcp.run()
