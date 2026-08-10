from rich.console import Console
from rich.table import Table
from devagent.core.models import GapReport

console = Console()

def render_gap_report_compact(report: GapReport) -> None:
    """Renders a compact version of the gap report for the chat session."""
    reuse_cnt = len(report.reuse)
    extend_cnt = len(report.extend)
    conflict_cnt = len(report.conflicts)
    new_cnt = len(report.net_new)
    total_cnt = reuse_cnt + extend_cnt + conflict_cnt + new_cnt

    console.print()
    console.print(f"[bold cyan]{total_cnt} requirements:[/bold cyan] "
                  f"{reuse_cnt} reuse · {extend_cnt} extend · "
                  f"[red]{conflict_cnt} conflict[/red] · {new_cnt} net new")
    console.print()

    table = Table(box=None, padding=(0, 2))
    table.add_column("ID", style="bold")
    table.add_column("Status")
    table.add_column("Matches")

    all_analyses = report.reuse + report.extend + report.conflicts + report.net_new
    for a in all_analyses:
        status_color = "green" if a.status.value == "FULLY_EXISTS" else "yellow" if a.status.value == "PARTIALLY_EXISTS" else "red" if a.status.value == "CONFLICTED" else "blue"
        matches = ", ".join(a.matched_files) if a.matched_files else "-"
        table.add_row(a.requirement.id, f"[{status_color}]{a.status.value}[/{status_color}]", matches)
    
    console.print(table)
    console.print()

    if report.edge_cases:
        console.print("[bold]Edge Cases:[/bold]")
        for ec in report.edge_cases:
            console.print(f"  • {ec.description}")
        console.print()

    e = report.effort_estimate
    console.print(f"[bold]Effort:[/bold] {e.total_days} days (Confidence: {e.confidence})")

def render_conflicts_only(report: GapReport) -> None:
    """Renders only the conflicts section for the chat session."""
    if not report.conflicts:
        console.print("[green]No conflicts found in this analysis.[/green]")
        return
        
    console.print(f"\n[bold red]Conflicts ({len(report.conflicts)})[/bold red]\n")
    
    for a in report.conflicts:
        req = a.requirement
        cd = a.conflict_details
        if not cd:
            continue
            
        console.print(f"[bold]{req.id}[/bold]: {req.description}")
        console.print(f"  [red]Severity:[/red] {cd.conflict_severity}")
        console.print(f"  [dim]Files:[/dim] {', '.join(cd.affected_files) if cd.affected_files else 'None'}")
        console.print(f"  [dim]Details:[/dim] {cd.explanation}\n")
