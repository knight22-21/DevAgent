"""Search tools: grep (text search), glob (file patterns), symbol lookup."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

from devagent.tools.registry import ToolRegistry

_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


def register_search_tools(registry: ToolRegistry, project_root: str = ".") -> None:
    root = Path(project_root).resolve()

    def grep_code(args: dict) -> str:
        pattern = args.get("pattern", "")
        glob = args.get("glob", "")
        case_sensitive = args.get("case_sensitive", True)
        max_results = min(int(args.get("max_results", 50)), 200)
        context = int(args.get("context_lines", 0))

        if not pattern:
            return "[error] pattern is required"

        # Try ripgrep first; fall back to Python grep
        rg_result = _try_ripgrep(root, pattern, glob, case_sensitive, max_results, context)
        if rg_result is not None:
            return rg_result

        return _python_grep(root, pattern, glob, case_sensitive, max_results, context)

    def find_files(args: dict) -> str:
        pattern = args.get("pattern", "*")
        path = args.get("path", ".")
        max_results = min(int(args.get("max_results", 100)), 500)

        try:
            search_root = (root / path).resolve()
            if not str(search_root).startswith(str(root)):
                return "[error] path escapes project root"
        except Exception as exc:
            return f"[error] {exc}"

        matches: list[str] = []
        for p in search_root.rglob("*"):
            if any(skip in p.parts for skip in _SKIP_DIRS):
                continue
            if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                matches.append(p.relative_to(root).as_posix())
                if len(matches) >= max_results:
                    break

        if not matches:
            return f"No files matching {pattern!r} found"
        return "\n".join(sorted(matches))

    registry.register(
        "grep",
        (
            "Search for a text pattern (regex) in project files. "
            "Use glob to restrict file types (e.g. '*.py'). "
            "Returns matching lines with file path and line number."
        ),
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search"},
                "glob": {"type": "string", "description": "File glob filter, e.g. '*.py'"},
                "case_sensitive": {"type": "boolean", "default": True},
                "max_results": {"type": "integer", "default": 50},
                "context_lines": {"type": "integer", "default": 0, "description": "Lines of context around each match"},
            },
            "required": ["pattern"],
        },
        grep_code,
    )

    registry.register(
        "find_files",
        "Find files in the project by name pattern (glob). Returns relative paths.",
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.ts'"},
                "path": {"type": "string", "description": "Sub-directory to search in", "default": "."},
                "max_results": {"type": "integer", "default": 100},
            },
        },
        find_files,
    )


def _try_ripgrep(
    root: Path,
    pattern: str,
    glob: str,
    case_sensitive: bool,
    max_results: int,
    context: int,
) -> str | None:
    """Try to use ripgrep. Returns None if rg is not installed."""
    cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
    if not case_sensitive:
        cmd.append("-i")
    if glob:
        cmd.extend(["--glob", glob])
    if context:
        cmd.extend(["-C", str(context)])
    cmd.extend(["--", pattern, str(root)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = result.stdout.splitlines()
        if len(lines) > max_results:
            lines = lines[:max_results]
            lines.append(f"... (truncated to {max_results} results)")
        return "\n".join(lines) if lines else "(no matches)"
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return "[error] grep timed out"


def _python_grep(
    root: Path,
    pattern: str,
    glob: str,
    case_sensitive: bool,
    max_results: int,
    context: int,
) -> str:
    """Pure-Python grep fallback."""
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return f"[error] Invalid regex: {exc}"

    results: list[str] = []
    count = 0

    for filepath in root.rglob("*"):
        if not filepath.is_file():
            continue
        if any(skip in filepath.parts for skip in _SKIP_DIRS):
            continue
        if glob and not fnmatch.fnmatch(filepath.name, glob):
            continue

        try:
            lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:  # noqa: S112
            continue

        rel = filepath.relative_to(root).as_posix()
        for i, line in enumerate(lines, start=1):
            if rx.search(line):
                if context:
                    start = max(0, i - 1 - context)
                    end = min(len(lines), i + context)
                    block = [
                        f"{rel}:{j + 1}: {lines[j]}"
                        for j in range(start, end)
                    ]
                    results.extend(block)
                    results.append("--")
                else:
                    results.append(f"{rel}:{i}: {line}")
                count += 1
                if count >= max_results:
                    results.append(f"... (truncated to {max_results} matches)")
                    return "\n".join(results)

    return "\n".join(results) if results else "(no matches)"
