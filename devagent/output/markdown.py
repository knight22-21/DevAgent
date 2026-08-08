"""Markdown output renderer."""

from __future__ import annotations

import re
from pathlib import Path

from devagent.core.models import GapReport, RequirementAnalysis
from devagent.core.storage import get_reports_dir


def _clean_filename(source: str) -> str:
    """Clean the spec source string to be safe for filenames."""
    # e.g., 'https://github.com/owner/repo/issues/123' -> 'issue-123'
    if "issues/" in source:
        issue_num = source.split("issues/")[-1].split("/")[0]
        return f"issue-{issue_num}"
    
    # Generic cleanup
    clean = re.sub(r'[^a-zA-Z0-9_-]', '_', source)
    return clean[:30].strip('_')


def _render_analysis_section(title: str, analyses: list[RequirementAnalysis]) -> str:
    if not analyses:
        return f"### {title}\n*No requirements in this category.*\n\n"
        
    lines = [f"### {title}\n"]
    for a in analyses:
        req = a.requirement
        lines.append(f"#### {req.id}: {req.description}")
        lines.append(f"- **Type:** {req.requirement_type.value}")
        lines.append(f"- **Priority:** {req.priority}")
        
        if a.matched_files:
            lines.append(f"- **Matched Files:** `{', '.join(a.matched_files)}`")
        if a.matched_functions:
            lines.append(f"- **Matched Functions:** `{', '.join(a.matched_functions)}`")
            
        if a.conflict_details:
            cd = a.conflict_details
            lines.append(f"- **🚨 CONFLICT ({cd.conflict_severity}):** {cd.explanation}")
            
        lines.append(f"- **Reasoning:** {a.classification_reason}")
        lines.append("")
        
    return "\n".join(lines)


def generate_markdown_report(report: GapReport, project_root: Path, project_name: str) -> str:
    """Generate a markdown report and save it to the disk.
    
    Returns:
        The absolute path to the saved markdown file.
    """
    date_str = report.generated_at.strftime("%Y-%m-%d")
    time_str = report.generated_at.strftime("%H%M%S")
    clean_src = _clean_filename(report.spec_source)
    
    filename = f"{clean_src}-{date_str}-{time_str}.md"
    reports_dir = get_reports_dir(project_root)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = reports_dir / filename
    
    lines = [
        f"# DevAgent Gap Analysis: {project_name}",
        "",
        f"**Source:** {report.spec_source}  ",
        f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  ",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        ""
    ]
    
    # Effort Estimate
    est = report.effort_estimate
    lines.extend([
        "### Effort Estimate",
        f"- **Total Days:** {est.total_days:.1f} days (Confidence: {est.confidence})",
        f"- **Conflict Resolution:** {est.conflict_resolution_hours:.1f}h",
        f"- **Extension:** {est.extension_hours:.1f}h",
        f"- **Net New:** {est.net_new_hours:.1f}h",
        f"- **Testing:** {est.testing_hours:.1f}h",
        f"- *Notes:* {est.notes}",
        "",
        "---",
        ""
    ])
    
    # Gap Analysis
    lines.append("## 2. Gap Analysis\n")
    lines.append(_render_analysis_section("✅ REUSE (Fully Exists)", report.reuse))
    lines.append(_render_analysis_section("⚠️ EXTEND (Partially Exists)", report.extend))
    lines.append(_render_analysis_section("❌ CONFLICT (Requires Resolution)", report.conflicts))
    lines.append(_render_analysis_section("🔨 NET NEW (Missing)", report.net_new))
    lines.append("---\n")
    
    # Implementation Order
    lines.append("## 3. Recommended Implementation Order\n")
    if report.implementation_order:
        for i, req_id in enumerate(report.implementation_order, 1):
            lines.append(f"{i}. [ ] {req_id}")
    else:
        lines.append("*No specific order recommended.*")
    lines.append("\n---\n")
    
    # Edge Cases
    lines.append("## 4. Edge Cases & Open Questions\n")
    if report.edge_cases:
        for ec in report.edge_cases:
            marker = "❗ MUST DISCUSS" if ec.severity == "must_discuss" else "❓ SHOULD DISCUSS"
            rel = f" (Related: {ec.related_requirement_id})" if ec.related_requirement_id else ""
            lines.append(f"- **{marker}:** {ec.description}{rel}")
    else:
        lines.append("*No edge cases identified.*")
    lines.append("\n---\n")
    
    # Data Models & APIs
    lines.append("## 5. Architectural Changes\n")
    
    lines.append("### Data Models")
    if report.data_models:
        for dm in report.data_models:
            status = "New" if dm.is_new else "Modified"
            lines.append(f"- **{dm.name}** ({status}): {dm.description}")
            lines.append(f"  - Fields: `{', '.join(dm.fields)}`")
    else:
        lines.append("*No data model changes identified.*")
    lines.append("")
        
    lines.append("### API Changes")
    if report.api_changes:
        for ac in report.api_changes:
            status = "New" if ac.is_new else "Modified"
            lines.append(f"- **{ac.method} {ac.endpoint}** ({status}): {ac.description}")
    else:
        lines.append("*No API changes identified.*")
        
    # Write to file
    content = "\n".join(lines)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    return str(file_path.resolve())
