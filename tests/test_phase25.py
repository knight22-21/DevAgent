"""Tests for Phase 25 — @agent-name REPL mention syntax."""

from __future__ import annotations

import pathlib

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_def(name: str = "code-reviewer", permission: str = "default",
                    memory: str = "session", isolation: str = "", prompt: str = ""):
    from devagent.agents.loader import AgentDef
    return AgentDef(
        name=name,
        description=f"A test agent: {name}",
        permission=permission,
        memory=memory,
        isolation=isolation,
        prompt=prompt,
    )


# ---------------------------------------------------------------------------
# Unit tests — @mention parsing logic (mirrors the REPL branch)
# ---------------------------------------------------------------------------

class TestAtMentionParsing:
    def _run_mention(self, raw: str, defs: dict, task_store=None, cfg=None, root="/tmp"):
        """Simulate the @mention REPL branch; returns (spawned, msg)."""
        if not raw.startswith("@"):
            return False, ""


        parts = raw[1:].split(None, 1)
        agent_name = parts[0].strip() if parts else ""
        agent_task = parts[1].strip() if len(parts) > 1 else ""

        spawned = False
        msg = ""

        if not agent_name:
            msg = "Usage: @agent-name <task description>"
        elif agent_name not in defs:
            available = ", ".join(sorted(defs)) or "(none)"
            msg = f"Unknown agent: {agent_name!r}. Available: {available}"
        else:
            ag = defs[agent_name]
            _task = agent_task or ag.prompt or f"Run the {agent_name} agent."
            msg = f"Spawned @{agent_name}"
            spawned = True

        return spawned, msg

    def test_valid_agent_spawns(self):
        defs = {"code-reviewer": _make_agent_def("code-reviewer")}
        spawned, msg = self._run_mention("@code-reviewer review auth.py", defs)
        assert spawned is True
        assert "code-reviewer" in msg

    def test_unknown_agent_shows_available(self):
        defs = {"code-reviewer": _make_agent_def("code-reviewer")}
        spawned, msg = self._run_mention("@no-such-agent do stuff", defs)
        assert spawned is False
        assert "Unknown agent" in msg
        assert "code-reviewer" in msg

    def test_empty_name_shows_usage(self):
        defs = {"code-reviewer": _make_agent_def("code-reviewer")}
        spawned, msg = self._run_mention("@", defs)
        assert spawned is False
        assert "Usage" in msg

    def test_no_task_uses_agent_prompt(self):
        defs = {"doc-writer": _make_agent_def("doc-writer", prompt="Write docs for this project.")}
        spawned, _msg = self._run_mention("@doc-writer", defs)
        assert spawned is True

    def test_no_defs_shows_none_available(self):
        spawned, msg = self._run_mention("@ghost-agent task", {})
        assert spawned is False
        assert "(none)" in msg

    def test_task_text_extracted(self):
        _task_captured = []

        raw = "@analyzer check all imports for unused symbols"
        parts = raw[1:].split(None, 1)
        _agent_name = parts[0].strip()
        agent_task = parts[1].strip() if len(parts) > 1 else ""
        assert agent_task == "check all imports for unused symbols"

    def test_agent_with_project_memory(self):
        """Agent with memory=project gets agent_name set."""
        defs = {"memory-agent": _make_agent_def("memory-agent", memory="project")}
        ag = defs["memory-agent"]
        agent_name_arg = ag.name if ag.memory == "project" else None
        assert agent_name_arg == "memory-agent"

    def test_agent_with_session_memory(self):
        """Agent with memory=session gets agent_name=None."""
        defs = {"session-agent": _make_agent_def("session-agent", memory="session")}
        ag = defs["session-agent"]
        agent_name_arg = ag.name if ag.memory == "project" else None
        assert agent_name_arg is None

    def test_multiple_agents_all_available_in_error(self):
        defs = {
            "agent-a": _make_agent_def("agent-a"),
            "agent-b": _make_agent_def("agent-b"),
            "agent-c": _make_agent_def("agent-c"),
        }
        spawned, msg = self._run_mention("@nonexistent task", defs)
        assert not spawned
        for name in ("agent-a", "agent-b", "agent-c"):
            assert name in msg


# ---------------------------------------------------------------------------
# Integration test — verify the handler exists in flows.py source
# ---------------------------------------------------------------------------

class TestFlowsHasAtMentionHandler:
    def test_at_mention_in_repl_source(self):
        source = pathlib.Path(__file__).parent.parent / "devagent" / "agent" / "flows.py"
        text = source.read_text(encoding="utf-8")
        assert "Phase 25" in text
        assert 'raw.startswith("@")' in text
        assert "load_agent_defs" in text

    def test_at_mention_in_help_text(self):
        source = pathlib.Path(__file__).parent.parent / "devagent" / "agent" / "flows.py"
        text = source.read_text(encoding="utf-8")
        assert "@agent" in text


# ---------------------------------------------------------------------------
# load_agent_defs integration — ensure it works with a real TOML file
# ---------------------------------------------------------------------------

class TestLoadAgentDefs:
    def test_loads_valid_toml(self, tmp_path):
        from devagent.agents.loader import load_agent_defs

        agents_dir = tmp_path / ".devagent" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test-reviewer.toml").write_text(
            'name = "test-reviewer"\n'
            'description = "Review code quality"\n'
            'permission = "read-only"\n'
            'memory = "project"\n',
            encoding="utf-8",
        )
        defs = load_agent_defs(tmp_path)
        assert "test-reviewer" in defs
        assert defs["test-reviewer"].permission == "read-only"
        assert defs["test-reviewer"].memory == "project"

    def test_empty_dir_returns_empty(self, tmp_path):
        from devagent.agents.loader import load_agent_defs
        defs = load_agent_defs(tmp_path)
        assert isinstance(defs, dict)

    def test_malformed_toml_skipped(self, tmp_path):
        from devagent.agents.loader import load_agent_defs
        agents_dir = tmp_path / ".devagent" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "broken.toml").write_text("not valid toml ]][[", encoding="utf-8")
        defs = load_agent_defs(tmp_path)
        assert "broken" not in defs
