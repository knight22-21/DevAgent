"""Phase 20 — Per-agent persistent MEMORY.md tests."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# ProjectMemory.for_agent — path derivation
# ---------------------------------------------------------------------------

class TestProjectMemoryForAgent:
    def test_path_is_under_agent_memory_dir(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory.for_agent(tmp_path, "my-agent")
        expected = tmp_path / ".devagent" / "agent-memory" / "my-agent" / "memory.md"
        assert pm.path == expected

    def test_sanitises_slashes_in_name(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory.for_agent(tmp_path, "some/agent")
        assert "/" not in pm.path.name
        assert "\\" not in str(pm.path.name)

    def test_default_path_unchanged(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory(tmp_path)
        assert pm.path == tmp_path / ".devagent" / "memory.md"

    def test_path_override_works(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        custom = tmp_path / "custom" / "memory.md"
        pm = ProjectMemory(tmp_path, path=custom)
        assert pm.path == custom


# ---------------------------------------------------------------------------
# ProjectMemory.for_agent — load / save / upsert / delete round-trip
# ---------------------------------------------------------------------------

class TestAgentMemoryReadWrite:
    def test_load_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory.for_agent(tmp_path, "agent-x")
        assert pm.load() == {}

    def test_upsert_creates_file_in_agent_dir(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory.for_agent(tmp_path, "agent-x")
        pm.upsert("key", "value")
        assert pm.path.exists()
        assert "key: value" in pm.path.read_text()

    def test_upsert_and_load_round_trip(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory.for_agent(tmp_path, "agent-x")
        pm.upsert("lang", "Python")
        pm.upsert("test_cmd", "pytest -q")
        data = pm.load()
        assert data["lang"] == "Python"
        assert data["test_cmd"] == "pytest -q"

    def test_agents_have_separate_memory_files(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm_a = ProjectMemory.for_agent(tmp_path, "agent-a")
        pm_b = ProjectMemory.for_agent(tmp_path, "agent-b")
        pm_a.upsert("exclusive", "a-data")
        assert pm_b.load() == {}

    def test_agent_memory_separate_from_project_memory(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm_project = ProjectMemory(tmp_path)
        pm_agent = ProjectMemory.for_agent(tmp_path, "my-agent")
        pm_project.upsert("global_key", "global_val")
        assert pm_agent.load() == {}

    def test_delete_removes_key(self, tmp_path: Path) -> None:
        from devagent.session.project_memory import ProjectMemory
        pm = ProjectMemory.for_agent(tmp_path, "agent-x")
        pm.upsert("to_remove", "bye")
        pm.delete("to_remove")
        assert "to_remove" not in pm.load()


# ---------------------------------------------------------------------------
# AgentDef memory field round-trip
# ---------------------------------------------------------------------------

class TestAgentDefMemoryField:
    def test_default_is_session(self) -> None:
        from devagent.agents.loader import AgentDef
        ad = AgentDef(name="test")
        assert ad.memory == "session"

    def test_project_memory_accepted(self) -> None:
        from devagent.agents.loader import AgentDef
        ad = AgentDef(name="test", memory="project")
        assert ad.memory == "project"

    def test_load_from_toml_memory_project(self, tmp_path: Path) -> None:
        from devagent.agents.loader import load_agent_defs
        agents_dir = tmp_path / ".devagent" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "myagent.toml").write_text(
            'name = "myagent"\nmemory = "project"\n'
        )
        defs = load_agent_defs(tmp_path)
        assert defs["myagent"].memory == "project"
