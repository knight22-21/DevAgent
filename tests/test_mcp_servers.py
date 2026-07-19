"""Tests for MCP servers."""
"""
Phase 2 Verification Test Script
Tests that all 5 MCP servers launch correctly and respond to tool calls.
"""
import asyncio
from pathlib import Path

from specsync.core.config import load_config, save_config, SpecSyncConfig
from specsync.core.storage import get_config_path
from specsync.mcp.manager import MCPManager


async def test_mcp_servers():
    """Test each MCP server by calling one tool."""
    
    # Load config
    config = load_config()
    print(f"✓ Config loaded from: {get_config_path()}")
    
    # Don't disable search provider anymore since we have a local SearchX server
    
    # Use current directory as project root for testing
    project_root = Path.cwd()
    print(f"✓ Project root: {project_root}")
    
    async with MCPManager(config, project_root) as manager:
        print("\n=== Testing MCP Servers ===\n")
        
        # Test GitHub MCP
        try:
            if config.github.token:
                # Try to list repositories (lightweight call)
                result = await manager.github.search_code(
                    query="test",
                    owner="octocat",
                    repo="Hello-World"
                )
                print("✓ GitHub MCP: responsive")
            else:
                print("⊘ GitHub MCP: skipped (no token configured)")
        except Exception as e:
            print(f"✗ GitHub MCP: {e}")
        
        # Test Filesystem MCP
        try:
            result = await manager.filesystem.list_directory(str(project_root))
            print("✓ Filesystem MCP: responsive")
        except Exception as e:
            print(f"✗ Filesystem MCP: {e}")
        
        # Test Search Provider (Brave or SearchX)
        try:
            if config.search_provider == "brave" and config.brave.api_key:
                result = await manager.brave.brave_web_search(
                    query="test",
                    count=1
                )
                print("✓ Brave Search MCP: responsive")
            elif config.search_provider == "searchx" and config.searchx.api_key:
                result = await manager.searchx.searchx_web_search(
                    query="test",
                    count=1
                )
                print("✓ SearchX MCP: responsive")
            else:
                print(f"⊘ Search Provider MCP: skipped (no {config.search_provider} API key configured)")
        except Exception as e:
            print(f"✗ Search Provider MCP: {e}")
        
        # Test SpecAnalysisMCP
        try:
            result = await manager.spec_analysis.parse_spec_to_requirements(
                spec_text="Add a simple login feature",
                context="Test context"
            )
            print("✓ SpecAnalysisMCP: responsive")
        except Exception as e:
            print(f"✗ SpecAnalysisMCP: {e}")
        
        # Test CodeSearchMCP
        try:
            result = await manager.code_search.get_import_graph(str(project_root))
            print("✓ CodeSearchMCP: responsive")
        except Exception as e:
            print(f"✗ CodeSearchMCP: {e}")
    
    print("\n=== All MCP servers shut down cleanly ===\n")


if __name__ == "__main__":
    asyncio.run(test_mcp_servers())