"""Chunking logic, AST parsing, embedding, ChromaDB write."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pathspec
from sentence_transformers import SentenceTransformer

# We will let the searcher/server handle ChromaDB and SQLite DB instances.
# The indexer handles the pure logic of chunking and embedding.


@dataclass
class CodeChunk:
    content: str
    chunk_type: str
    name: str
    file_path: str
    start_line: int
    end_line: int


def _get_source_segment(source_lines: list[str], node: ast.AST) -> str:
    """Extract the exact source lines for an AST node."""
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        return ""
    if node.end_lineno is None:
        return ""
    # AST lines are 1-indexed, list is 0-indexed
    return "\n".join(source_lines[node.lineno - 1:node.end_lineno])


def chunk_python_file(file_path: str, source_code: str) -> list[CodeChunk]:
    """Parse Python source code and return semantic chunks using AST."""
    chunks = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # If it doesn't parse, fall back to generic chunking
        return chunk_generic_file(file_path, source_code)

    source_lines = source_code.splitlines()

    # Get module-level docstring and imports
    module_lines = []
    if ast.get_docstring(tree):
        module_lines.append(f'"""{ast.get_docstring(tree)}"""\n')
    
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)):
            module_lines.append(_get_source_segment(source_lines, node))

    if module_lines:
        content = "\n".join(module_lines)
        chunks.append(CodeChunk(
            content=content,
            chunk_type="module",
            name=Path(file_path).stem,
            file_path=file_path,
            start_line=1,
            end_line=tree.body[-1].end_lineno if tree.body else 1
        ))

    # Process classes and functions
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            content = _get_source_segment(source_lines, node)
            if content:
                chunks.append(CodeChunk(
                    content=content,
                    chunk_type="function",
                    name=node.name,
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno
                ))
        elif isinstance(node, ast.ClassDef):
            # Class chunk (signature + docstring + init + method names)
            class_lines = []
            for dec in node.decorator_list:
                class_lines.append(_get_source_segment(source_lines, dec))
            class_lines.append(f"class {node.name}:")
            if ast.get_docstring(node):
                class_lines.append(f'    """{ast.get_docstring(node)}"""')
            
            methods = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(child.name)
                    if child.name == "__init__":
                        class_lines.append("    " + _get_source_segment(source_lines, child).replace("\n", "\n    "))
            
            if methods:
                class_lines.append(f"    # Methods: {', '.join(methods)}")
                
            chunks.append(CodeChunk(
                content="\n".join(class_lines),
                chunk_type="class",
                name=node.name,
                file_path=file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno
            ))
            
            # Individual method chunks
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    content = _get_source_segment(source_lines, child)
                    if content:
                        chunks.append(CodeChunk(
                            content=content,
                            chunk_type="method",
                            name=f"{node.name}.{child.name}",
                            file_path=file_path,
                            start_line=child.lineno,
                            end_line=child.end_lineno or child.lineno
                        ))

    return chunks


def chunk_generic_file(file_path: str, source_code: str) -> list[CodeChunk]:
    """Chunk non-Python files by splitting at blank lines into ~150 line blocks."""
    lines = source_code.splitlines()
    if len(lines) <= 200:
        return [CodeChunk(
            content=source_code,
            chunk_type="file",
            name=Path(file_path).name,
            file_path=file_path,
            start_line=1,
            end_line=len(lines)
        )]
        
    chunks = []
    current_chunk: list[str] = []
    start_idx = 0
    
    for i, line in enumerate(lines):
        current_chunk.append(line)
        if len(current_chunk) >= 150 and not line.strip():
            chunks.append(CodeChunk(
                content="\n".join(current_chunk),
                chunk_type="chunk",
                name=f"{Path(file_path).name}_part{len(chunks)+1}",
                file_path=file_path,
                start_line=start_idx + 1,
                end_line=i + 1
            ))
            current_chunk = []
            start_idx = i + 1
            
    if current_chunk:
        chunks.append(CodeChunk(
            content="\n".join(current_chunk),
            chunk_type="chunk",
            name=f"{Path(file_path).name}_part{len(chunks)+1}",
            file_path=file_path,
            start_line=start_idx + 1,
            end_line=len(lines)
        ))
        
    return chunks


def is_ignored(file_path: Path, root_dir: Path, gitignore_spec: pathspec.PathSpec | None) -> bool:
    """Check if a file should be ignored during indexing."""
    rel_path = file_path.relative_to(root_dir).as_posix()
    
    # Built-in ignores
    built_in = [
        "node_modules", ".venv", "venv", "env", ".env", "__pycache__", ".git", 
        "dist", "build", ".idea", ".vscode"
    ]
    parts = Path(rel_path).parts
    if any(p in built_in for p in parts):
        return True
        
    if file_path.suffix in [".pyc", ".pyo", ".egg-info", ".exe", ".dll", ".so", ".png", ".jpg", ".jpeg"]:
        return True
        
    if gitignore_spec and gitignore_spec.match_file(rel_path):
        return True
        
    return False


def get_gitignore_spec(root_dir: Path) -> pathspec.PathSpec | None:
    """Parse .gitignore if it exists."""
    gitignore_path = root_dir / ".gitignore"
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, lines)
    return None
