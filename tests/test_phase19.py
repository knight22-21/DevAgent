"""Phase 19 — DEVAGENT.md prose format, ancestor scoping, and init-project tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from devagent.agent.system_prompt import load_devagent_md

# ---------------------------------------------------------------------------
# load_devagent_md — basic cases
# ---------------------------------------------------------------------------

class TestLoadDevagentMd:
    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        assert load_devagent_md(tmp_path) == ""

    def test_returns_content_from_project_root(self, tmp_path: Path) -> None:
        (tmp_path / "DEVAGENT.md").write_text("# project\nmy instructions")
        result = load_devagent_md(tmp_path)
        assert "my instructions" in result

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        (tmp_path / "DEVAGENT.md").write_text("  content  \n\n")
        assert load_devagent_md(tmp_path) == "content"


# ---------------------------------------------------------------------------
# load_devagent_md — ancestor scoping
# ---------------------------------------------------------------------------

class TestAncestorScoping:
    def test_ancestor_included_before_project(self, tmp_path: Path) -> None:
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / "DEVAGENT.md").write_text("# parent\nteam conventions")
        (child / "DEVAGENT.md").write_text("# project\nproject-specific")

        result = load_devagent_md(child)
        assert "team conventions" in result
        assert "project-specific" in result
        # parent (most general) comes first
        assert result.index("team conventions") < result.index("project-specific")

    def test_only_ancestor_no_project_file(self, tmp_path: Path) -> None:
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / "DEVAGENT.md").write_text("# global\nglobal rules")

        result = load_devagent_md(child)
        assert "global rules" in result

    def test_no_ancestor_only_project_file(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir()
        (project / "DEVAGENT.md").write_text("# project\nonly project")

        result = load_devagent_md(project)
        assert "only project" in result

    def test_multiple_ancestors_ordered_outermost_first(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = a / "b"
        c = b / "c"
        c.mkdir(parents=True)
        (a / "DEVAGENT.md").write_text("level-a")
        (b / "DEVAGENT.md").write_text("level-b")
        (c / "DEVAGENT.md").write_text("level-c")

        result = load_devagent_md(c)
        assert result.index("level-a") < result.index("level-b") < result.index("level-c")

    def test_separator_between_files(self, tmp_path: Path) -> None:
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / "DEVAGENT.md").write_text("parent content")
        (child / "DEVAGENT.md").write_text("child content")

        result = load_devagent_md(child)
        assert "---" in result


# ---------------------------------------------------------------------------
# _collect_project_context
# ---------------------------------------------------------------------------

class TestCollectProjectContext:
    def test_includes_directory_listing(self, tmp_path: Path) -> None:
        from devagent.cli import _collect_project_context
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("hello")

        ctx = _collect_project_context(tmp_path)
        assert "src/" in ctx
        assert "tests/" in ctx

    def test_includes_pyproject_toml(self, tmp_path: Path) -> None:
        from devagent.cli import _collect_project_context
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"')

        ctx = _collect_project_context(tmp_path)
        assert "myapp" in ctx

    def test_includes_readme_excerpt(self, tmp_path: Path) -> None:
        from devagent.cli import _collect_project_context
        (tmp_path / "README.md").write_text("My Project\n\nDoes cool stuff.")

        ctx = _collect_project_context(tmp_path)
        assert "Does cool stuff" in ctx

    def test_handles_missing_files_gracefully(self, tmp_path: Path) -> None:
        from devagent.cli import _collect_project_context
        ctx = _collect_project_context(tmp_path)
        assert isinstance(ctx, str)


# ---------------------------------------------------------------------------
# init-project CLI — static template
# ---------------------------------------------------------------------------

class TestInitProjectStatic:
    def test_creates_devagent_md(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["init-project", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "DEVAGENT.md").exists()

    def test_creates_devagent_memory_dir(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        runner = CliRunner()
        runner.invoke(app, ["init-project", str(tmp_path)])
        assert (tmp_path / ".devagent" / "memory.md").exists()

    def test_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        (tmp_path / "DEVAGENT.md").write_text("existing")
        runner = CliRunner()
        result = runner.invoke(app, ["init-project", str(tmp_path)])
        assert result.exit_code != 0
        assert (tmp_path / "DEVAGENT.md").read_text() == "existing"

    def test_force_overwrites(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        (tmp_path / "DEVAGENT.md").write_text("existing")
        runner = CliRunner()
        result = runner.invoke(app, ["init-project", str(tmp_path), "--force"])
        assert result.exit_code == 0
        assert (tmp_path / "DEVAGENT.md").read_text() != "existing"


# ---------------------------------------------------------------------------
# init-project --generate (mocked LLM)
# ---------------------------------------------------------------------------

class TestInitProjectGenerate:
    def test_generate_writes_llm_content(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app
        from devagent.core.llm import LLMResponse

        mock_resp = LLMResponse(content="# DEVAGENT.md\n\n## Tech stack\nPython 3.12")
        runner = CliRunner()

        with patch("devagent.core.llm.LLMClient") as MockLLM:
            instance = MockLLM.return_value
            instance.complete.return_value = mock_resp
            result = runner.invoke(app, ["init-project", str(tmp_path), "--generate"])

        assert result.exit_code == 0
        text = (tmp_path / "DEVAGENT.md").read_text()
        assert "Python 3.12" in text

    def test_generate_falls_back_on_llm_error(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from devagent.cli import app

        runner = CliRunner()
        with patch("devagent.core.llm.LLMClient") as MockLLM:
            instance = MockLLM.return_value
            instance.complete.side_effect = RuntimeError("no model")
            result = runner.invoke(app, ["init-project", str(tmp_path), "--generate"])

        assert result.exit_code == 0
        assert (tmp_path / "DEVAGENT.md").exists()
