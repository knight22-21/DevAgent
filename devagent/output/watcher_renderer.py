"""Rich rendering for F3 Repo Health Monitor output."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devagent.core.models import (
    IssueComplexity,
    WatcherAnalysis,
    WatchHealthReport,
)

console = Console()

_COMPLEXITY_COLOR = {
    IssueComplexity.LOW: "green",
    IssueComplexity.MEDIUM: "yellow",
    IssueComplexity.HIGH: "red",
}

_SEVERITY_COLOR = {"high": "red", "medium": "yellow", "low": "dim"}


def render_health_report(report: WatchHealthReport) -> None:
    """Renders the full health report after a check run."""
    console.print()
    console.print(
        Panel(
            f"[bold]HEALTH REPORT[/bold]  ·  "
            f"{report.owner}/{report.repo}  ·  "
            f"{report.new_issues_count} new issue"
            f"{'s' if report.new_issues_count != 1 else ''}",
            border_style="cyan",
        )
    )

    if not report.new_analyses:
        console.print("  [dim]No new issues to report.[/dim]")
        return

    # Issues table
    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("Issue", style="bold", width=8)
    table.add_column("Title", width=40)
    table.add_column("Complexity", width=10)
    table.add_column("Reqs", width=6)
    table.add_column("Conflicts", width=10)
    table.add_column("Files", width=6)

    for analysis in report.new_analyses:
        color = _COMPLEXITY_COLOR[analysis.complexity]
        table.add_row(
            f"#{analysis.issue_number}",
            analysis.issue_title[:38] + ("…" if len(analysis.issue_title) > 38 else ""),
            f"[{color}]{analysis.complexity.value.capitalize()}[/{color}]",
            str(analysis.requirements_count),
            str(analysis.conflicts_count) if analysis.conflicts_count == 0
            else f"[red]{analysis.conflicts_count}[/red]",
            str(len(analysis.touched_files)),
        )

    console.print(table)

    # Cross-issue conflicts section
    if report.cross_issue_conflicts:
        console.print()
        console.print(
            Panel(
                "[bold]CROSS-ISSUE CONFLICTS[/bold]  —  "
                "these files are touched by multiple open issues",
                border_style="yellow",
            )
        )

        for conflict in report.cross_issue_conflicts:
            color = _SEVERITY_COLOR[conflict.severity]
            issue_refs = " and ".join(f"#{n}" for n in conflict.issue_numbers)
            console.print(
                f"  [{color}]⚠[/{color}]  "
                f"[bold]{conflict.file_path}[/bold]  "
                f"touched by {issue_refs}  "
                f"[dim]({conflict.severity} severity)[/dim]"
            )

        console.print()
        console.print(
            "[dim]  Tip: Assign cross-conflict files to the same developer, "
            "or coordinate before starting work.[/dim]"
        )

    console.print()
    console.print(
        "[dim]  Run 'devagent watch --show ISSUE_NUMBER' for full analysis of any issue.[/dim]"
    )
    console.print(
        "[dim]  Run 'devagent watch --report' to see all analysed issues.[/dim]"
    )


def render_watched_repos(repos: list) -> None:
    """Renders the list of watched repos for 'devagent watch --list'."""
    if not repos:
        console.print("[dim]No repos currently being watched.[/dim]")
        console.print(
            "[dim]Run 'devagent watch --repo owner/repo' to start watching a repo.[/dim]"
        )
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("Repo", width=30)
    table.add_column("Status", width=10)
    table.add_column("Interval", width=12)
    table.add_column("Last checked", width=20)
    table.add_column("Filters", width=20)

    for repo in repos:
        last_checked = (
            repo.last_checked_at.strftime("%Y-%m-%d %H:%M")
            if repo.last_checked_at
            else "Never"
        )
        filters = ", ".join(repo.issue_filters) if repo.issue_filters else "All issues"
        status = "[green]Active[/green]" if repo.is_active else "[dim]Stopped[/dim]"

        table.add_row(
            f"{repo.owner}/{repo.repo}",
            status,
            f"Every {repo.check_interval_minutes}m",
            last_checked,
            filters,
        )

    console.print(table)


def render_all_analyses(analyses: list[WatcherAnalysis], owner: str, repo: str) -> None:
    """Renders all stored analyses for 'devagent watch --report'."""
    if not analyses:
        console.print(f"[dim]No issues analysed yet for {owner}/{repo}.[/dim]")
        return

    console.print()
    console.print(
        Panel(
            f"[bold]All Analysed Issues[/bold]  ·  {owner}/{repo}  ·  {len(analyses)} total",
            border_style="dim",
        )
    )

    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("Issue", width=8)
    table.add_column("Title", width=45)
    table.add_column("Complexity", width=10)
    table.add_column("Conflicts", width=10)
    table.add_column("Full report", width=12)

    for analysis in analyses:
        color = _COMPLEXITY_COLOR[analysis.complexity]
        has_report = "[green]✓[/green]" if analysis.full_report_available else "[dim]—[/dim]"

        table.add_row(
            f"#{analysis.issue_number}",
            analysis.issue_title[:43] + ("…" if len(analysis.issue_title) > 43 else ""),
            f"[{color}]{analysis.complexity.value.capitalize()}[/{color}]",
            str(analysis.conflicts_count)
            if analysis.conflicts_count == 0
            else f"[red]{analysis.conflicts_count}[/red]",
            has_report,
        )

    console.print(table)
    console.print(
        "[dim]  Run 'devagent watch --show ISSUE_NUMBER' for full analysis.[/dim]"
    )
