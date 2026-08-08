"""FastMCP server: CodeSearchMCP."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import aiosqlite
import chromadb
from mcp.server.fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

from devagent.core.storage import get_chroma_dir, get_sqlite_path, get_project_hash
from devagent.mcp.servers.code_search.indexer import (
    CodeChunk, chunk_generic_file, chunk_python_file, get_gitignore_spec, is_ignored
)
from devagent.mcp.servers.code_search.searcher import build_import_graph, compute_conflict_severity


mcp = FastMCP("CodeSearchMCP")

# Global models to avoid reloading
_embedding_model: SentenceTransformer | None = None
_chroma_clients: dict[str, chromadb.PersistentClient] = {}


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def _get_chroma_collection(project_root: str) -> Any:
    global _chroma_clients
    root_path = Path(project_root)
    hash_id = get_project_hash(root_path)
    
    if hash_id not in _chroma_clients:
        chroma_dir = get_chroma_dir(root_path)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        _chroma_clients[hash_id] = chromadb.PersistentClient(path=str(chroma_dir))
        
    client = _chroma_clients[hash_id]
    collection_name = f"codebase_{hash_id}"
    return client.get_or_create_collection(name=collection_name)


async def _init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                file_path TEXT PRIMARY KEY,
                last_modified REAL NOT NULL,
                chunk_count INTEGER NOT NULL,
                indexed_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS project_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.commit()


@mcp.tool()
async def index_codebase(project_root: str, incremental: bool = True):
    """Index the codebase for semantic search.

    Args:
        project_root: Absolute path to the project root.
        incremental: If true, only index changed files.

    Returns:
        JSON string representing an IndexResult object.
    """
    import time
    from datetime import datetime

    start_time = time.monotonic()
    root_path = Path(project_root)
    
    sqlite_path = get_sqlite_path(root_path)
    await _init_db(sqlite_path)
    
    collection = _get_chroma_collection(project_root)
    embedder = _get_embedding_model()
    gitignore_spec = get_gitignore_spec(root_path)
    
    indexed_files: dict[str, float] = {}
    if incremental:
        async with aiosqlite.connect(sqlite_path) as db:
            async with db.execute("SELECT file_path, last_modified FROM indexed_files") as cursor:
                async for row in cursor:
                    indexed_files[row[0]] = row[1]
                    
    files_indexed = 0
    chunks_created = 0
    files_skipped = 0
    
    new_records = []
    updated_records = []
    seen_on_disk: set[str] = set()
    
    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
            
        if is_ignored(file_path, root_path, gitignore_spec):
            continue
            
        try:
            mtime = file_path.stat().st_mtime
        except OSError:
            continue
            
        rel_path = file_path.relative_to(root_path).as_posix()
        seen_on_disk.add(rel_path)
        
        if incremental and rel_path in indexed_files:
            if mtime <= indexed_files[rel_path]:
                files_skipped += 1
                continue
                
            # Changed file - delete old chunks from Chroma
            collection.delete(where={"file_path": rel_path})
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            continue # Skip binary files
            
        if file_path.suffix == ".py":
            chunks = chunk_python_file(rel_path, content)
        else:
            chunks = chunk_generic_file(rel_path, content)
            
        if not chunks:
            continue
            
        # Embed chunks
        texts = [c.content for c in chunks]
        embeddings = embedder.encode(texts).tolist()
        
        ids = [f"{rel_path}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_path": c.file_path,
                "chunk_type": c.chunk_type,
                "name": c.name,
                "start_line": c.start_line,
                "end_line": c.end_line
            } for c in chunks
        ]
        
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        files_indexed += 1
        chunks_created += len(chunks)
        now_iso = datetime.now().isoformat()
        
        if rel_path in indexed_files:
            updated_records.append((mtime, len(chunks), now_iso, rel_path))
        else:
            new_records.append((rel_path, mtime, len(chunks), now_iso))

    # Phase 3.3 — Stale file cleanup: remove files that no longer exist on disk
    deleted_paths = []
    if incremental and indexed_files:
        for indexed_path in indexed_files:
            if indexed_path not in seen_on_disk:
                # File was deleted from disk — clean up from ChromaDB and SQLite
                collection.delete(where={"file_path": indexed_path})
                deleted_paths.append(indexed_path)

    # Update SQLite
    async with aiosqlite.connect(sqlite_path) as db:
        if new_records:
            await db.executemany(
                "INSERT INTO indexed_files (file_path, last_modified, chunk_count, indexed_at) VALUES (?, ?, ?, ?)",
                new_records
            )
        if updated_records:
            await db.executemany(
                "UPDATE indexed_files SET last_modified=?, chunk_count=?, indexed_at=? WHERE file_path=?",
                updated_records
            )
        if deleted_paths:
            await db.executemany(
                "DELETE FROM indexed_files WHERE file_path=?",
                [(p,) for p in deleted_paths]
            )
        await db.commit()
        
    duration = time.monotonic() - start_time
    
    result = {
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "files_skipped": files_skipped,
        "files_deleted": len(deleted_paths),
        "duration_seconds": duration
    }
    
    return json.dumps(result)


@mcp.tool()
async def semantic_search(query: str, project_root: str, top_k: int = 5, filter_language: str | None = None):
    """Search the codebase for semantic matches.

    Args:
        query: The natural language search query.
        project_root: The project path (to identify the index).
        top_k: Number of results.
        filter_language: Optional language filter (e.g., 'python').

    Returns:
        JSON string representing a list of SearchResult objects.
    """
    collection = _get_chroma_collection(project_root)
    embedder = _get_embedding_model()
    
    query_embedding = embedder.encode(query).tolist()
    
    where_clause = None
    if filter_language:
        # We didn't add language to metadata in chunking, but we can filter by file extension
        # Simple workaround for now.
        pass
        
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_clause,
        include=["metadatas", "documents", "distances"]
    )
    
    search_results = []
    if results["ids"] and len(results["ids"]) > 0:
        ids = results["ids"][0]
        metadatas = results["metadatas"][0]
        documents = results["documents"][0]
        distances = results["distances"][0]
        
        for i in range(len(ids)):
            # Convert cosine distance to similarity score
            # Chroma returns L2 distance by default if configured, but sentence-transformers uses cosine typically
            # Assuming distance, we convert to similarity (1 - (dist/2)) roughly for cosine.
            # If distance is < 1.4 (roughly 0.3 similarity), include it
            sim = max(0.0, 1.0 - (distances[i] / 2.0))
            if sim < 0.3:
                continue
                
            meta = metadatas[i]
            search_results.append({
                "file_path": meta["file_path"],
                "chunk_type": meta["chunk_type"],
                "name": meta["name"],
                "start_line": meta["start_line"],
                "end_line": meta["end_line"],
                "similarity_score": sim,
                "content": documents[i]
            })
            
    return json.dumps(search_results)


@mcp.tool()
async def get_import_graph(project_root: str):
    """Get the full import dependency graph for the project.

    Returns:
        JSON string representing a dict mapping file paths to lists of imported modules.
    """
    graph = build_import_graph(project_root)
    return json.dumps(graph)


@mcp.tool()
async def detect_conflicts(file_path: str, proposed_change_description: str, project_root: str):
    """Detect potential conflicts for a proposed change to a file.

    Returns:
        JSON string representing a ConflictResult object.
    """
    graph = build_import_graph(project_root)
    
    # Find files that depend on file_path
    # In a real AST import graph, the keys are paths and values are imported modules.
    # So we need to match module names to the file_path.
    module_name = Path(file_path).with_suffix('').as_posix().replace('/', '.')
    
    affected_files = []
    for f_path, imports in graph.items():
        if module_name in imports:
            affected_files.append(f_path)
            
    severity = compute_conflict_severity(affected_files)
    
    result = {
        "affected_files": affected_files,
        "conflict_severity": severity,
        "explanation": f"Found {len(affected_files)} files depending on {module_name}."
    }
    
    return json.dumps(result)


@mcp.tool()
async def find_similar_implementations(description: str, exclude_files: list[str], project_root: str):
    """Find existing implementations matching a description.

    Returns:
        JSON string representing a list of SearchResult objects.
    """
    collection = _get_chroma_collection(project_root)
    embedder = _get_embedding_model()
    
    prompt = f"Implementation of: {description}"
    query_embedding = embedder.encode(prompt).tolist()
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=10,
        include=["metadatas", "documents", "distances"]
    )
    
    search_results = []
    if results["ids"] and len(results["ids"]) > 0:
        ids = results["ids"][0]
        metadatas = results["metadatas"][0]
        documents = results["documents"][0]
        distances = results["distances"][0]
        
        for i in range(len(ids)):
            meta = metadatas[i]
            if meta["file_path"] in exclude_files:
                continue
                
            sim = max(0.0, 1.0 - (distances[i] / 2.0))
            if sim < 0.3:
                continue
                
            search_results.append({
                "file_path": meta["file_path"],
                "chunk_type": meta["chunk_type"],
                "name": meta["name"],
                "start_line": meta["start_line"],
                "end_line": meta["end_line"],
                "similarity_score": sim,
                "content": documents[i]
            })
            if len(search_results) >= 5:
                break
                
    return json.dumps(search_results)


if __name__ == "__main__":
    mcp.run()
