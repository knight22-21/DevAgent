import os
import pytest
from pathlib import Path

from specsync.core.storage import (
    get_project_hash,
    ensure_dirs,
    get_project_dir,
    get_chroma_dir,
    get_sqlite_path,
    get_reports_dir,
    init_db,
    get_index_status,
)


def test_project_hash_deterministic():
    path1 = Path("C:/Users/Test/Project")
    path2 = Path("c:\\users\\test\\project")  # Should be normalized in storage?
    
    # Actually the hash is just SHA256 of the string, so let's test determinism
    # for the exact same path string.
    hash1 = get_project_hash(path1)
    hash2 = get_project_hash(path1)
    
    assert hash1 == hash2
    assert len(hash1) == 64


def test_directories_created(temp_project_dir: Path, monkeypatch, tmp_path):
    # Mock the base user data dir so it doesn't write to real AppData
    monkeypatch.setattr("platformdirs.user_data_path", lambda *args, **kwargs: tmp_path / "specsync_data")
    
    ensure_dirs(temp_project_dir)
    
    proj_dir = get_project_dir(temp_project_dir)
    assert proj_dir.exists()
    assert proj_dir.is_dir()
    
    chroma_dir = get_chroma_dir(temp_project_dir)
    assert chroma_dir.exists()
    
    reports_dir = get_reports_dir(temp_project_dir)
    assert reports_dir.exists()


@pytest.mark.asyncio
async def test_sqlite_schema_creation(temp_project_dir: Path, tmp_path):
    sqlite_path = tmp_path / "test.db"
    
    # Run init
    await init_db(sqlite_path)
    
    assert sqlite_path.exists()
    
    # Check status
    status = await get_index_status(sqlite_path)
    assert status["exists"] is True
    assert status["total_files"] == 0
    assert status["total_chunks"] == 0
    assert status["last_indexed"] is None
