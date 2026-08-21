"""CodePrism tool registrations for the agent tool registry.

All tools are prefixed cp_ to make it clear they use the knowledge graph
rather than raw file I/O, and to let the LLM choose intelligently.

Tool taxonomy:
  cp_get_context      — callers/callees/types around a symbol (replaces grep+read)
  cp_get_impact       — what breaks if this symbol changes (pre-edit safety)
  cp_get_callers      — all callers of a function
  cp_search_symbol    — find symbols by name/kind
  cp_get_data_flow    — trace data through the codebase
  cp_get_file_map     — compact project structure (replaces list_files)
  cp_get_module_summary — high-level file overview
  cp_get_dependencies — import graph for a file
  cp_undo_write       — undo the last CodePrism-tracked write
  cp_get_stats        — knowledge graph statistics
"""

from __future__ import annotations

import json
from typing import Any

from devagent.codeprism.client import CodePrismClient
from devagent.tools.registry import ToolRegistry


def register_codeprism_tools(registry: ToolRegistry, client: CodePrismClient) -> None:
    """Register all cp_* tools using the provided CodePrismClient."""

    def _json(d: dict) -> str:
        if "error" in d:
            return f"[cp_error] {d['error']}"
        return json.dumps(d, indent=2)

    # ------------------------------------------------------------------
    # cp_get_context
    # ------------------------------------------------------------------
    def cp_get_context(args: dict) -> str:
        file = args.get("file", "")
        symbol = args.get("symbol", "")
        depth = int(args.get("depth", 2))
        if not file or not symbol:
            return "[error] file and symbol are required"
        result = client.get_context(file, symbol, depth)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        # Also record the read in the session overlay
        client.record_read(file, symbol)
        return _fmt_context(result)

    registry.register(
        "cp_get_context",
        (
            "Get callers, callees, related types, and variables for a code symbol "
            "from the CodePrism knowledge graph. Much cheaper than read_file + grep. "
            "depth=1 (direct neighbours), depth=2 (default, 2 hops), depth=3 (transitive)."
        ),
        {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Relative path to the source file"},
                "symbol": {"type": "string", "description": "Symbol name (function, class, variable)"},
                "depth": {"type": "integer", "default": 2, "description": "Graph traversal depth (1-3)"},
            },
            "required": ["file", "symbol"],
        },
        cp_get_context,
    )

    # ------------------------------------------------------------------
    # cp_get_impact
    # ------------------------------------------------------------------
    def cp_get_impact(args: dict) -> str:
        file = args.get("file", "")
        symbol = args.get("symbol", "")
        if not file or not symbol:
            return "[error] file and symbol are required"
        result = client.get_impact(file, symbol)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        return _fmt_impact(result)

    registry.register(
        "cp_get_impact",
        (
            "Estimate the impact of changing a symbol: direct dependents, transitive "
            "dependents, severity (LOW/MEDIUM/HIGH/CRITICAL), and affected test files. "
            "Run this before editing a function or class."
        ),
        {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "symbol": {"type": "string"},
            },
            "required": ["file", "symbol"],
        },
        cp_get_impact,
    )

    # ------------------------------------------------------------------
    # cp_get_callers
    # ------------------------------------------------------------------
    def cp_get_callers(args: dict) -> str:
        file = args.get("file", "")
        function = args.get("function", "")
        if not file or not function:
            return "[error] file and function are required"
        result = client.get_callers(file, function)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = [f"Callers of {function!r} in {file} ({result['count']} total):"]
        for c in result.get("callers", []):
            lines.append(f"  {c['file']}:{c.get('line', '?')}  {c['name']}")
        return "\n".join(lines)

    registry.register(
        "cp_get_callers",
        "List all functions that call a given function, with file and line number.",
        {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "function": {"type": "string"},
            },
            "required": ["file", "function"],
        },
        cp_get_callers,
    )

    # ------------------------------------------------------------------
    # cp_search_symbol
    # ------------------------------------------------------------------
    def cp_search_symbol(args: dict) -> str:
        query = args.get("query", "")
        kind = args.get("kind")
        if not query:
            return "[error] query is required"
        result = client.search_symbol(query, kind)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = [f"Found {result['count']} symbol(s) matching {query!r}:"]
        for m in result.get("matches", [])[:20]:
            lines.append(
                f"  {m['file']}:{m.get('line', '?')}  "
                f"[{m['kind']}] {m['name']}"
                + (f"  — {m['docstring']}" if m.get("docstring") else "")
            )
        if result["count"] > 20:
            lines.append(f"  ... ({result['count'] - 20} more, refine the query)")
        return "\n".join(lines)

    registry.register(
        "cp_search_symbol",
        (
            "Find symbols (functions, classes, variables) by name substring. "
            "kind filter: function | class | variable | import"
        ),
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Substring to search for"},
                "kind": {
                    "type": "string",
                    "enum": ["function", "class", "variable", "import"],
                    "description": "Optional kind filter",
                },
            },
            "required": ["query"],
        },
        cp_search_symbol,
    )

    # ------------------------------------------------------------------
    # cp_get_callees
    # ------------------------------------------------------------------
    def cp_get_callees(args: dict) -> str:
        file = args.get("file", "")
        function = args.get("function", "")
        if not file or not function:
            return "[error] file and function are required"
        result = client.get_callees(file, function)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = [f"Callees of {function!r} in {file} ({result['count']} total):"]
        for c in result.get("callees", []):
            lines.append(f"  {c['file']}:{c.get('line', '?')}  {c['name']}")
        return "\n".join(lines)

    registry.register(
        "cp_get_callees",
        "List all functions called by a given function (its direct dependencies), with file and line number.",
        {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "function": {"type": "string"},
            },
            "required": ["file", "function"],
        },
        cp_get_callees,
    )

    # ------------------------------------------------------------------
    # cp_get_data_flow
    # ------------------------------------------------------------------
    def cp_get_data_flow(args: dict) -> str:
        file = args.get("file", "")
        symbol = args.get("symbol", "")
        if not file or not symbol:
            return "[error] file and symbol are required"
        result = client.get_data_flow(file, symbol)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        return _fmt_data_flow(result)

    registry.register(
        "cp_get_data_flow",
        "Trace where data from a symbol flows: sources, sinks, and intermediate nodes.",
        {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "symbol": {"type": "string"},
            },
            "required": ["file", "symbol"],
        },
        cp_get_data_flow,
    )

    # ------------------------------------------------------------------
    # cp_get_file_map
    # ------------------------------------------------------------------
    def cp_get_file_map(args: dict) -> str:
        result = client.get_file_map()
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = [
            f"Project: {result.get('project_path', '.')}",
            f"Files: {result['total_files']}  Symbols: {result['total_symbols']}",
            "",
        ]
        for e in result.get("entries", []):
            role = f"  — {e['role']}" if e.get("role") else ""
            lines.append(f"  {e['path']}  ({e.get('symbols', 0)} symbols){role}")
        return "\n".join(lines)

    registry.register(
        "cp_get_file_map",
        (
            "Get a compact project-wide file map with per-file role summaries. "
            "Use this as the first step to understand project structure — "
            "far cheaper than list_files + reading each file."
        ),
        {"type": "object", "properties": {}},
        cp_get_file_map,
    )

    # ------------------------------------------------------------------
    # cp_get_module_summary
    # ------------------------------------------------------------------
    def cp_get_module_summary(args: dict) -> str:
        file = args.get("file", "")
        if not file:
            return "[error] file is required"
        result = client.get_module_summary(file)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = [
            f"File: {result['file']}",
            f"Purpose: {result['purpose']}",
            f"Complexity: {result.get('complexity_score', 0):.1f}",
        ]
        if result.get("test_coverage_file"):
            lines.append(f"Tests: {result['test_coverage_file']}")
        if result.get("public_api"):
            lines.append("Public API: " + ", ".join(s["name"] for s in result["public_api"][:10]))
        if result.get("dependencies"):
            lines.append("Imports: " + ", ".join(result["dependencies"][:8]))
        if result.get("key_classes"):
            lines.append("Key classes: " + ", ".join(s["name"] for s in result["key_classes"]))
        return "\n".join(lines)

    registry.register(
        "cp_get_module_summary",
        "Get a high-level narrative summary of a source file without reading its full content.",
        {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Relative path to the file"},
            },
            "required": ["file"],
        },
        cp_get_module_summary,
    )

    # ------------------------------------------------------------------
    # cp_get_dependencies
    # ------------------------------------------------------------------
    def cp_get_dependencies(args: dict) -> str:
        file = args.get("file", "")
        if not file:
            return "[error] file is required"
        result = client.get_dependencies(file)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = [f"Dependencies of {file}:"]
        if result.get("internal_deps"):
            lines.append("  Internal: " + ", ".join(result["internal_deps"]))
        if result.get("external_deps"):
            lines.append("  External: " + ", ".join(result["external_deps"]))
        if result.get("circular_deps"):
            lines.append("  [WARNING] Circular: " + ", ".join(result["circular_deps"]))
        if not result.get("internal_deps") and not result.get("external_deps"):
            lines.append("  (no dependencies found)")
        return "\n".join(lines)

    registry.register(
        "cp_get_dependencies",
        "Show all internal and external dependencies (imports) of a file.",
        {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
            },
            "required": ["file"],
        },
        cp_get_dependencies,
    )

    # ------------------------------------------------------------------
    # cp_undo_write
    # ------------------------------------------------------------------
    def cp_undo_write(args: dict) -> str:
        steps = int(args.get("steps", 1))
        result = client.undo_write(steps)
        if "error" in result:
            return f"[cp_error] {result['error']}"
        restored = result.get("files_restored", [])
        if not restored:
            return "Nothing to undo."
        return f"Undone {result.get('steps_undone', steps)} write(s): " + ", ".join(restored)

    registry.register(
        "cp_undo_write",
        "Undo the last N file writes tracked by CodePrism and restore the previous content.",
        {
            "type": "object",
            "properties": {
                "steps": {"type": "integer", "default": 1, "description": "Number of writes to undo"},
            },
        },
        cp_undo_write,
    )

    # ------------------------------------------------------------------
    # cp_get_stats
    # ------------------------------------------------------------------
    def cp_get_stats(args: dict) -> str:
        result = client.get_stats()
        if "error" in result:
            return f"[cp_error] {result['error']}"
        lines = ["CodePrism knowledge graph:"]
        for k, v in result.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    registry.register(
        "cp_get_stats",
        "Show CodePrism knowledge graph statistics (file count, symbol count, etc.).",
        {"type": "object", "properties": {}},
        cp_get_stats,
    )


# ---------------------------------------------------------------------------
# Text formatters for tool output
# ---------------------------------------------------------------------------

def _fmt_context(r: dict) -> str:
    sym = r.get("symbol", {})
    lines = [
        f"Symbol: {sym.get('name', '?')} [{sym.get('kind', '?')}]  "
        f"line {sym.get('line', '?')}  {'(public)' if sym.get('is_public') else '(private)'}",
        f"Signature: {sym.get('signature', '(none)')}",
        f"Estimated tokens if read raw: ~{r.get('estimated_tokens', '?')}",
    ]
    callers = r.get("direct_callers", [])
    if callers:
        lines.append(f"\nCallers ({len(callers)}):")
        for s in callers[:6]:
            lines.append(f"  {s['file']}:{s.get('line', '?')}  {s['name']}")
    callees = r.get("direct_callees", [])
    if callees:
        lines.append(f"\nCallees ({len(callees)}):")
        for s in callees[:6]:
            lines.append(f"  {s['file']}:{s.get('line', '?')}  {s['name']}")
    types = r.get("related_types", [])
    if types:
        lines.append(f"\nRelated types: " + ", ".join(s["name"] for s in types[:5]))
    return "\n".join(lines)


def _fmt_impact(r: dict) -> str:
    sev = r.get("severity", "UNKNOWN")
    surface = r.get("estimated_change_surface", 0)
    pub = " [PUBLIC API]" if r.get("public_api_affected") else ""
    lines = [
        f"Impact of changing {r.get('symbol', '?')}: {sev}{pub}",
        f"Change surface: {surface} transitive dependent(s)",
    ]
    direct = r.get("direct_dependents", [])
    if direct:
        lines.append(f"\nDirect dependents ({len(direct)}):")
        for s in direct[:6]:
            lines.append(f"  {s['file']}:{s.get('line', '?')}  {s['name']}")
    tests = r.get("affected_test_files", [])
    if tests:
        lines.append(f"\nAffected tests: " + ", ".join(tests[:5]))
    trans = r.get("transitive_dependents", [])
    if trans:
        shown = trans[:4]
        lines.append(
            f"\nTransitive ({len(trans)}): "
            + ", ".join(s["name"] for s in shown)
            + (f" +{len(trans)-4} more" if len(trans) > 4 else "")
        )
    return "\n".join(lines)


def _fmt_data_flow(r: dict) -> str:
    lines = [f"Data flow for {r.get('symbol', '?')}:"]
    if r.get("sources"):
        lines.append("  Sources: " + ", ".join(str(s) for s in r["sources"][:6]))
    if r.get("sinks"):
        lines.append("  Sinks: " + ", ".join(str(s) for s in r["sinks"][:6]))
    if r.get("intermediate_nodes"):
        lines.append("  Intermediate: " + ", ".join(str(s) for s in r["intermediate_nodes"][:6]))
    paths = r.get("flow_paths", [])
    if paths:
        lines.append(f"  Paths ({len(paths)}): " + " → ".join(str(n) for n in paths[0][:5]))
    return "\n".join(lines)
