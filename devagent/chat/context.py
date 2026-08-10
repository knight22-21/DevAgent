from devagent.core.models import GapReport

def estimate_prompt_tokens(text: str) -> int:
    """Rough token estimator."""
    return len(text) // 4

def build_system_prompt(report: GapReport, project_name: str) -> str:
    """Builds the system prompt that grounds the LLM in the gap report."""
    
    header = f"""You are DevAgent Chat, an assistant that helps developers understand and plan
implementation work based on a codebase gap analysis.

You have been given a complete gap analysis report for a specific GitHub issue
or specification. Your job is to answer questions about this analysis: explain
findings, help prioritize work, surface risks, and assist with planning.

Strict rules you must follow:
- Only answer questions about this specific gap analysis. Do not answer general
  coding questions, write code, or discuss topics unrelated to this report.
- If asked to write code, say: "I help with planning and understanding, not
  writing code. Use the gap report as your implementation guide."
- If asked about something not in the report, say so clearly rather than
  guessing or making something up.
- Base every answer on the specific data in the report below. Name specific
  files, functions, and requirements when relevant.
- Keep answers concise but complete. Use bullet points for lists of items.
  Do not pad answers.

PROJECT: {project_name}
SPEC SOURCE: {report.spec_source}
ANALYZED AT: {report.generated_at}
TOTAL REQUIREMENTS: {len(report.reuse) + len(report.extend) + len(report.conflicts) + len(report.net_new)}

━━━ REQUIREMENTS AND STATUS ━━━
"""

    lines = [header]
    
    # Render all requirement analyses across all categories
    all_analyses = report.reuse + report.extend + report.conflicts + report.net_new
    for a in all_analyses:
        req = a.requirement
        lines.append(f"\n[{req.id}] {req.description}")
        lines.append(f"  Type: {req.requirement_type.value}")
        lines.append(f"  Priority: {req.priority}")
        lines.append(f"  Status: {a.status.value}")
        
        if a.status.value in ("FULLY_EXISTS", "PARTIALLY_EXISTS"):
            if a.matched_files:
                lines.append(f"    Matched in: {', '.join(a.matched_files)}")
            if a.matched_functions:
                lines.append(f"    Matched functions: {', '.join(a.matched_functions)}")
                
        if a.status.value == "CONFLICTED" and a.conflict_details:
            cd = a.conflict_details
            lines.append(f"    Conflict severity: {cd.conflict_severity}")
            if cd.affected_files:
                lines.append(f"    Affected files ({len(cd.affected_files)}): {', '.join(cd.affected_files)}")
            lines.append(f"    Conflict explanation: {cd.explanation}")
            
        lines.append(f"  Classification reason: {a.classification_reason}")

    lines.append("\n━━━ EDGE CASES ━━━\n")
    if report.edge_cases:
        for ec in report.edge_cases:
            related = f" (Related to: REQ-{ec.related_requirement_id})" if ec.related_requirement_id else ""
            lines.append(f"- {ec.description} [{ec.severity}]{related}")
    else:
        lines.append("No edge cases identified.")

    lines.append("\n━━━ DATA MODEL CHANGES ━━━\n")
    if report.data_models:
        for dm in report.data_models:
            lines.append(f"- {dm.name} {'(New)' if dm.is_new else '(Modified)'}: {dm.description}")
    else:
        lines.append("No data model changes identified.")

    lines.append("\n━━━ API CHANGES ━━━\n")
    if report.api_changes:
        for ac in report.api_changes:
            lines.append(f"- {ac.method} {ac.endpoint} {'(New)' if ac.is_new else '(Modified)'}: {ac.description}")
    else:
        lines.append("No API changes identified.")

    lines.append("\n━━━ IMPLEMENTATION ORDER ━━━\n")
    if report.implementation_order:
        for i, step in enumerate(report.implementation_order, 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("No specific order recommended.")

    lines.append("\n━━━ EFFORT ESTIMATE ━━━\n")
    e = report.effort_estimate
    lines.append(f"Conflict resolution: {e.conflict_resolution_hours}h")
    lines.append(f"Extensions: {e.extension_hours}h")
    lines.append(f"Net new work: {e.net_new_hours}h")
    lines.append(f"Testing: {e.testing_hours}h")
    lines.append(f"Total: {e.total_days} days (confidence: {e.confidence})")
    lines.append(f"Notes: {e.notes}")

    return "\n".join(lines)
