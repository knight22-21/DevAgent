"""Pipeline orchestrator: runs agents sequentially."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from specsync.agents.code_inventory import CodeInventoryAgent
from specsync.agents.gap_report import GapReportAgent
from specsync.agents.spec_parser import SpecParserAgent
from specsync.agents.state import PipelineState
from specsync.core.config import SpecSyncConfig
from specsync.core.models import GapReport
from specsync.mcp.manager import MCPManager


console = Console()


async def run_pipeline(
    config: SpecSyncConfig, 
    mcp_manager: MCPManager, 
    spec_text: str, 
    spec_source: str,
    project_root: str
) -> GapReport:
    """Run the full analysis pipeline end-to-end."""
    
    # Initialize agents
    parser = SpecParserAgent(config, mcp_manager)
    inventory = CodeInventoryAgent(config, mcp_manager, project_root)
    reporter = GapReportAgent(config)
    
    # Initial state
    state: PipelineState = {
        "spec_text": spec_text,
        "spec_source": spec_source,
        "search_context": "",
        "requirements": [],
        "edge_cases": [],
        "data_models": [],
        "api_changes": [],
        "requirement_analyses": [],
        "effort_estimate": None,
        "implementation_order": [],
        "gap_report": None
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        
        # 1. SpecParserAgent
        task1 = progress.add_task("[cyan]Parsing specification and extracting requirements...", total=None)
        try:
            state = await parser.app.ainvoke(state)
        except Exception as e:
            console.print(Panel(
                f"[red]SpecParserAgent failed:[/red]\n{str(e)}",
                title="❌ Pipeline Error",
                border_style="red"
            ))
            sys.exit(1)
        progress.update(task1, completed=100, visible=False)
            
        if not state.get("requirements"):
            console.print(Panel(
                "No requirements could be extracted from the spec. Try being more specific.",
                title="❌ Pipeline Error",
                border_style="red"
            ))
            sys.exit(1)
            
        # 2. CodeInventoryAgent
        task2 = progress.add_task("[cyan]Searching codebase and classifying requirements...", total=None)
        try:
            state = await inventory.app.ainvoke(state)
        except Exception as e:
            console.print(Panel(
                f"[red]CodeInventoryAgent failed:[/red]\n{str(e)}",
                title="❌ Pipeline Error",
                border_style="red"
            ))
            sys.exit(1)
        progress.update(task2, completed=100, visible=False)
            
        # 3. GapReportAgent
        task3 = progress.add_task("[cyan]Generating effort estimates and gap report...", total=None)
        try:
            state = await reporter.app.ainvoke(state)
        except Exception as e:
            console.print(Panel(
                f"[red]GapReportAgent failed:[/red]\n{str(e)}",
                title="❌ Pipeline Error",
                border_style="red"
            ))
            sys.exit(1)
        progress.update(task3, completed=100, visible=False)
            
    # Return the final report
    report = state.get("gap_report")
    if not report:
        console.print(Panel(
            "Pipeline completed but no gap report was generated.",
            title="❌ Pipeline Error",
            border_style="red"
        ))
        sys.exit(1)
        
    return report
