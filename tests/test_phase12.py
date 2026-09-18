"""Phase 12 — DEVAGENT.md + cross-session memory tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from devagent.agent.system_prompt import build_system_prompt, load_devagent_md
from devagent.session import store
from devagent.session.memory import MemoryBlock
from devagent.session.project_memory import ProjectMemory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def pm(tmp_project: Path) -> ProjectMemory:
    return ProjectMemory(tmp_project)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Initialized SQLite DB."""
    path = tmp_path / "test.db"
    store.init_schema(db_path=path)
    return path


def _new_session_id() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# ProjectMemory — load / save / upsert / delete
# ---------------------------------------------------------------------------

class TestProjectMemory:
    def test_load_missing_returns_empty(self, pm: ProjectMemory) -> None:
        assert pm.load() == {}

    def test_save_and_load_roundtrip(self, pm: ProjectMemory) -> None:
        pm.save({"framework": "FastAPI", "test_cmd": "pytest"})
        data = pm.load()
        assert data["framework"] == "FastAPI"
        assert data["test_cmd"] == "pytest"

    def test_upsert_new_key(self, pm: ProjectMemory) -> None:
        pm.upsert("lang", "Python")
        assert pm.load()["lang"] == "Python"

    def test_upsert_overwrites_existing(self, pm: ProjectMemory) -> None:
        pm.upsert("lang", "Python")
        pm.upsert("lang", "Go")
        assert pm.load()["lang"] == "Go"

    def test_delete_existing_key(self, pm: ProjectMemory) -> None:
        pm.save({"a": "1", "b": "2"})
        pm.delete("a")
        data = pm.load()
        assert "a" not in data
        assert data["b"] == "2"

    def test_delete_missing_key_is_noop(self, pm: ProjectMemory) -> None:
        pm.save({"x": "1"})
        pm.delete("nonexistent")
        assert pm.load() == {"x": "1"}

    def test_file_is_sorted(self, pm: ProjectMemory) -> None:
        pm.save({"z": "last", "a": "first", "m": "mid"})
        text = pm.path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
        keys = [ln.split(":")[0].lstrip("- ") for ln in lines]
        assert keys == sorted(keys)

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        pm2 = ProjectMemory(nested)
        pm2.upsert("key", "val")
        assert pm2.path.exists()


# ---------------------------------------------------------------------------
# ProjectMemory — file format
# ---------------------------------------------------------------------------

class TestProjectMemoryFormat:
    def test_header_present(self, pm: ProjectMemory) -> None:
        pm.save({"key": "val"})
        text = pm.path.read_text(encoding="utf-8")
        assert text.startswith("# DevAgent Memory")

    def test_auto_managed_comment(self, pm: ProjectMemory) -> None:
        pm.save({"k": "v"})
        assert "auto-managed" in pm.path.read_text(encoding="utf-8")

    def test_empty_after_all_deleted(self, pm: ProjectMemory) -> None:
        pm.save({"only": "one"})
        pm.delete("only")
        text = pm.path.read_text(encoding="utf-8")
        assert "only" not in text
        assert "# DevAgent Memory" in text


# ---------------------------------------------------------------------------
# load_devagent_md
# ---------------------------------------------------------------------------

class TestLoadDevagentMd:
    def test_returns_empty_when_missing(self, tmp_project: Path) -> None:
        assert load_devagent_md(tmp_project) == ""

    def test_reads_content(self, tmp_project: Path) -> None:
        (tmp_project / "DEVAGENT.md").write_text("## Tech stack\nPython", encoding="utf-8")
        result = load_devagent_md(tmp_project)
        assert "Python" in result

    def test_strips_whitespace(self, tmp_project: Path) -> None:
        (tmp_project / "DEVAGENT.md").write_text("  hello  \n\n", encoding="utf-8")
        assert load_devagent_md(tmp_project) == "hello"

    def test_handles_unreadable_path(self) -> None:
        assert load_devagent_md("/nonexistent/path/xyz") == ""


# ---------------------------------------------------------------------------
# build_system_prompt — devagent_md injection
# ---------------------------------------------------------------------------

class TestBuildSystemPromptPhase12:
    def test_devagent_md_injected(self) -> None:
        prompt = build_system_prompt(devagent_md="## Rules\nNo LangGraph")
        assert "Project Instructions (DEVAGENT.md)" in prompt
        assert "No LangGraph" in prompt

    def test_devagent_md_empty_omitted(self) -> None:
        prompt = build_system_prompt(devagent_md="")
        assert "DEVAGENT.md" not in prompt

    def test_devagent_md_after_project_description(self) -> None:
        prompt = build_system_prompt(
            project_description="My API",
            devagent_md="## Tech\nFastAPI",
        )
        proj_pos = prompt.index("My API")
        md_pos = prompt.index("FastAPI")
        assert proj_pos < md_pos

    def test_all_sections_combined(self) -> None:
        prompt = build_system_prompt(
            project_description="proj",
            devagent_md="## Conventions\nruff",
            extra_context="some context",
            memory_block="- key: val",
        )
        assert "proj" in prompt
        assert "ruff" in prompt
        assert "some context" in prompt
        assert "key: val" in prompt


# ---------------------------------------------------------------------------
# MemoryBlock — project_memory integration
# ---------------------------------------------------------------------------

class TestMemoryBlockProjectMemory:
    def test_project_facts_merged_on_load(self, pm: ProjectMemory, db: Path) -> None:
        pm.save({"lang": "Python", "test_cmd": "pytest"})
        sid = _new_session_id()
        mb = MemoryBlock(sid, db_path=db, project_memory=pm)
        assert mb.get("lang") == "Python"
        assert mb.get("test_cmd") == "pytest"

    def test_set_writes_to_file(self, pm: ProjectMemory, db: Path) -> None:
        sid = _new_session_id()
        mb = MemoryBlock(sid, db_path=db, project_memory=pm)
        mb.set("new_key", "hello")
        assert pm.load().get("new_key") == "hello"

    def test_delete_removes_from_file(self, pm: ProjectMemory, db: Path) -> None:
        pm.save({"to_remove": "yes"})
        sid = _new_session_id()
        mb = MemoryBlock(sid, db_path=db, project_memory=pm)
        mb.delete("to_remove")
        assert "to_remove" not in pm.load()

    def test_cross_session_persistence(self, pm: ProjectMemory, db: Path) -> None:
        """Facts written in session A should appear in a fresh session B."""
        sid_a = _new_session_id()
        mb_a = MemoryBlock(sid_a, db_path=db, project_memory=pm)
        mb_a.set("shared_fact", "cross-session")

        sid_b = _new_session_id()
        mb_b = MemoryBlock(sid_b, db_path=db, project_memory=pm)
        assert mb_b.get("shared_fact") == "cross-session"

    def test_no_project_memory_works(self, db: Path) -> None:
        sid = _new_session_id()
        mb = MemoryBlock(sid, db_path=db)
        mb.set("x", "1")
        assert mb.get("x") == "1"

    def test_session_fact_not_overwritten_by_file(self, pm: ProjectMemory, db: Path) -> None:
        """SQLite (session-level) facts take precedence over file facts for the same session."""
        pm.save({"key": "from_file"})
        sid = _new_session_id()
        mb1 = MemoryBlock(sid, db_path=db, project_memory=pm)
        mb1.set("key", "from_session")

        mb2 = MemoryBlock(sid, db_path=db, project_memory=pm)
        # Same session — SQLite already has the key so it won't be overwritten
        assert mb2.get("key") == "from_session"

    def test_as_prompt_block_includes_project_facts(self, pm: ProjectMemory, db: Path) -> None:
        pm.save({"framework": "FastAPI"})
        sid = _new_session_id()
        mb = MemoryBlock(sid, db_path=db, project_memory=pm)
        block = mb.as_prompt_block()
        assert "framework" in block
        assert "FastAPI" in block
