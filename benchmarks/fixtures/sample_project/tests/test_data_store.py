"""Tests for data_store — all pass even with the bug (tests basic behaviour)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_store import DataStore


def test_insert_and_get_all():
    ds = DataStore()
    ds.insert({"name": "alice", "age": 30})
    assert len(ds.get_all()) == 1


def test_search_returns_match():
    ds = DataStore()
    ds.insert({"name": "alice", "role": "admin"})
    ds.insert({"name": "bob", "role": "user"})
    results = ds.search("role", "admin")
    assert len(results) == 1
    assert results[0]["name"] == "alice"


def test_delete():
    ds = DataStore()
    ds.insert({"id": "1", "value": "x"})
    ds.insert({"id": "2", "value": "y"})
    removed = ds.delete("id", "1")
    assert removed == 1
    assert len(ds.get_all()) == 1
