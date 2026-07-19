"""Semantic search, import graph, conflict detection."""

from __future__ import annotations

import ast
from pathlib import Path

import radon.complexity as radon_comp


def build_import_graph(project_root: str) -> dict[str, list[str]]:
    """Build a graph of file dependencies based on AST imports."""
    root_path = Path(project_root)
    graph: dict[str, list[str]] = {}
    
    for file_path in root_path.rglob("*.py"):
        if any(part.startswith(".") or part in ["node_modules", "venv", ".venv", "__pycache__"] for part in file_path.parts):
            continue
            
        rel_path = file_path.relative_to(root_path).as_posix()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
            
        imports = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
                    
        graph[rel_path] = imports
        
    return graph


def compute_conflict_severity(affected_files: list[str]) -> str:
    """Estimate conflict severity based on the number of affected files."""
    count = len(affected_files)
    if count == 0:
        return "low"
    elif count <= 2:
        return "medium"
    else:
        return "high"
