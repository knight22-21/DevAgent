"""Terminal output renderer using Rich."""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from specsync.core.models import GapReport, RequirementAnalysis


console = Console()


def _truncate(text: str, max_length: int = 60) -> str:
    """Truncate text for table display."""
    if len(text) > max_length:
        return text[:max_length - 3] + "..."
    return text


def _render_analysis_list(title: str, analyses: list[RequirementAnalysis], style: str) -> Panel:
    """Helper to render a section of the gap analysis."""
    if not analyses:
        return Panel(f"[dim]No {title.lower()} requirements found.[/dim]", title=title, border_style=style)

    content = []
    for a in analyses:
        req = a.requirement
        item = Text()
        item.append(f"[{req.id}] ", style="bold")
        item.append(f"{_truncate(req.description, 80)}\n")
        
        if a.matched_files:
            item.append("  Files: ", style="dim")
            item.append(", ".join(a.matched_files) + "\n")
            
        if a.matched_functions:
            item.append("  Funcs: ", style="dim")
            item.append(", ".join(a.matched_functions) + "\n")
            
        if a.conflict_details:
            cd = a.conflict_details
            item.append(f"  Conflict ({cd.conflict_severity}): ", style="bold red")
            item.append(f"{cd.explanation}\n")
            
        content.append(item)

    return Panel(Group(*content), title=title, border_style=style)


def render_gap_report(report: GapReport, project_name: str, report_path: str | None = None) -> None:
    """Render the full gap report to the terminal."""
    console.print()
    
    # 1. Header
    header = Table.grid(padding=(0, 2))
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        f"[bold cyan]SpecSource:[/bold cyan] {report.spec_source}",
        f"[dim]{report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
    )
    header.add_row(f"[bold cyan]Project:[/bold cyan] {project_name}", "")
    
    console.print(Panel(header, title="📊 SpecSync Gap Analysis", border_style="cyan"))
    
    # 2. Requirements Table
    all_reqs = report.reuse + report.extend + report.conflicts + report.net_new
    if all_reqs:
        req_table = Table(title="Extracted Requirements", border_style="blue")
        req_table.add_column("ID", style="bold cyan")
        req_table.add_column("Type")
        req_table.add_column("Priority")
        req_table.add_column("Description")
        
        for a in all_reqs:
            req = a.requirement
            req_table.add_row(req.id, req.requirement_type.value, req.priority, _truncate(req.description))
            
        console.print(req_table)
        console.print()
        
    # 3. Gap Analysis Sections
    console.print(_render_analysis_list("✅ REUSE (Fully Exists)", report.reuse, "green"))
    console.print(_render_analysis_list("⚠️ EXTEND (Partially Exists)", report.extend, "yellow"))
    console.print(_render_analysis_list("❌ CONFLICT (Requires Resolution)", report.conflicts, "red"))
    console.print(_render_analysis_list("🔨 NET NEW (Missing)", report.net_new, "blue"))
    
    # 4. Edge Cases
    if report.edge_cases:
        ec_text = Text()
        for ec in report.edge_cases:
            related = f" (Related: {ec.related_requirement_id})" if ec.related_requirement_id else ""
            marker = "❗" if ec.severity == "must_discuss" else "❓"
            ec_text.append(f"{marker} {ec.description}{related}\n")
            
        console.print(Panel(ec_text, title="Edge Cases & Questions", border_style="yellow"))
        
    # 5. Implementation Order
    if report.implementation_order:
        order_text = Text()
        for i, req_id in enumerate(report.implementation_order, 1):
            order_text.append(f"{i}. {req_id}\n")
        console.print(Panel(order_text, title="Recommended Implementation Order", border_style="cyan"))
        
    # 6. Effort Estimate
    est = report.effort_estimate
    est_table = Table(title="Effort Estimate", border_style="magenta")
    est_table.add_column("Category")
    est_table.add_column("Hours", justify="right")
    
    est_table.add_row("Conflict Resolution", f"{est.conflict_resolution_hours:.1f}h")
    est_table.add_row("Extension", f"{est.extension_hours:.1f}h")
    est_table.add_row("Net New", f"{est.net_new_hours:.1f}h")
    est_table.add_row("Testing", f"{est.testing_hours:.1f}h")
    est_table.add_section()
    est_table.add_row("[bold]Total Days (8h/day)[/bold]", f"[bold]{est.total_days:.1f} days[/bold]")
    
    console.print(est_table)
    console.print(f"[dim]Confidence: {est.confidence} | Notes: {est.notes}[/dim]")
    console.print()
    
    # 7. Footer
    if report_path:
        console.print(f"📄 Full markdown report saved to: [cyan]{report_path}[/cyan]\n")
