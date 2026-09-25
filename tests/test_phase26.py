"""Tests for Phase 26 — plugin bundle format."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devagent.cli import app
from devagent.plugins import PluginBundle, install_plugin, load_plugins

runner = CliRunner()


# ---------------------------------------------------------------------------
# PluginBundle dataclass
# ---------------------------------------------------------------------------

class TestPluginBundle:
    def test_defaults(self):
        b = PluginBundle(name="test-plugin")
        assert b.name == "test-plugin"
        assert b.version == "0.0.0"
        assert b.description == ""
        assert b.skills == []
        assert b.hooks == []
        assert b.mcp_servers == []
        assert b.tools == []

    def test_full_construction(self):
        b = PluginBundle(
            name="docker-plugin",
            version="1.2.3",
            description="Docker tools for DevAgent",
            skills=[{"name": "docker-build", "prompt": "Build the docker image"}],
            hooks=[{"event": "session_start", "type": "prompt", "template": "Docker ready."}],
            mcp_servers=[{"name": "docker-mcp", "command": "docker-mcp"}],
            tools=["docker_run", "docker_logs"],
        )
        assert b.version == "1.2.3"
        assert len(b.skills) == 1
        assert len(b.hooks) == 1
        assert len(b.mcp_servers) == 1
        assert len(b.tools) == 2

    def test_separate_instances_dont_share_lists(self):
        a = PluginBundle(name="a")
        b = PluginBundle(name="b")
        a.skills.append({"name": "x"})
        assert b.skills == []


# ---------------------------------------------------------------------------
# load_plugins — entry point discovery
# ---------------------------------------------------------------------------

class TestLoadPlugins:
    def _make_ep(self, bundle_or_callable):
        ep = MagicMock()
        ep.load.return_value = bundle_or_callable
        return ep

    def test_empty_when_no_entry_points(self):
        with patch("devagent.plugins.entry_points", return_value=[]):
            bundles = load_plugins()
        assert bundles == []

    def test_loads_bundle_instance(self):
        bundle = PluginBundle(name="my-plugin", version="0.1.0")
        ep = self._make_ep(bundle)
        with patch("devagent.plugins.entry_points", return_value=[ep]):
            bundles = load_plugins()
        assert len(bundles) == 1
        assert bundles[0].name == "my-plugin"

    def test_loads_callable_returning_bundle(self):
        bundle = PluginBundle(name="callable-plugin", version="2.0.0")
        ep = self._make_ep(lambda: bundle)
        with patch("devagent.plugins.entry_points", return_value=[ep]):
            bundles = load_plugins()
        assert len(bundles) == 1
        assert bundles[0].version == "2.0.0"

    def test_skips_crashing_entry_point(self):
        good = PluginBundle(name="good-plugin")
        bad_ep = MagicMock()
        bad_ep.load.side_effect = ImportError("missing dep")
        good_ep = self._make_ep(good)
        with patch("devagent.plugins.entry_points", return_value=[bad_ep, good_ep]):
            bundles = load_plugins()
        assert len(bundles) == 1
        assert bundles[0].name == "good-plugin"

    def test_skips_non_bundle_entry_point(self):
        ep = self._make_ep("not-a-bundle")
        with patch("devagent.plugins.entry_points", return_value=[ep]):
            bundles = load_plugins()
        assert bundles == []

    def test_multiple_plugins_loaded(self):
        a = PluginBundle(name="plugin-a")
        b = PluginBundle(name="plugin-b")
        with patch("devagent.plugins.entry_points", return_value=[self._make_ep(a), self._make_ep(b)]):
            bundles = load_plugins()
        assert len(bundles) == 2
        names = {bu.name for bu in bundles}
        assert names == {"plugin-a", "plugin-b"}


# ---------------------------------------------------------------------------
# install_plugin
# ---------------------------------------------------------------------------

class TestInstallPlugin:
    def test_success(self):
        mock_result = MagicMock(returncode=0, stdout="Successfully installed pkg\n", stderr="")
        with patch("devagent.plugins.subprocess.run", return_value=mock_result):
            success, output = install_plugin("some-package")
        assert success is True
        assert "Successfully installed" in output

    def test_failure(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="ERROR: No matching distribution\n")
        with patch("devagent.plugins.subprocess.run", return_value=mock_result):
            success, output = install_plugin("no-such-package")
        assert success is False
        assert "ERROR" in output

    def test_uses_sys_executable(self):
        import sys
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("devagent.plugins.subprocess.run", return_value=mock_result) as mock_run:
            install_plugin("pkg")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable
        assert cmd[1:] == ["-m", "pip", "install", "pkg"]


# ---------------------------------------------------------------------------
# CLI — devagent plugins list
# ---------------------------------------------------------------------------

class TestPluginsListCli:
    def test_no_plugins_shows_hint(self):
        with patch("devagent.plugins.entry_points", return_value=[]):
            result = runner.invoke(app, ["plugins", "list"])
        assert result.exit_code == 0
        assert "No plugin bundles installed" in result.output

    def test_lists_installed_plugin(self):
        bundle = PluginBundle(
            name="docker-tools",
            version="1.0.0",
            description="Docker integration",
            skills=[{"name": "s1"}],
        )
        with patch("devagent.plugins.entry_points", return_value=[
            _make_bundle_ep(bundle)
        ]):
            result = runner.invoke(app, ["plugins", "list"])
        assert result.exit_code == 0
        assert "docker-tools" in result.output
        assert "1.0.0" in result.output

    def test_lists_multiple_plugins(self):
        a = PluginBundle(name="plugin-a", version="0.1")
        b = PluginBundle(name="plugin-b", version="0.2")
        with patch("devagent.plugins.entry_points", return_value=[
            _make_bundle_ep(a), _make_bundle_ep(b)
        ]):
            result = runner.invoke(app, ["plugins", "list"])
        assert result.exit_code == 0
        assert "plugin-a" in result.output
        assert "plugin-b" in result.output


# ---------------------------------------------------------------------------
# CLI — devagent plugins install
# ---------------------------------------------------------------------------

class TestPluginsInstallCli:
    def test_successful_install(self):
        mock_result = MagicMock(returncode=0, stdout="Successfully installed pkg", stderr="")
        with patch("devagent.plugins.subprocess.run", return_value=mock_result):
            result = runner.invoke(app, ["plugins", "install", "devagent-docker"])
        assert result.exit_code == 0
        assert "Installed" in result.output

    def test_failed_install_exits_1(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="ERROR: package not found")
        with patch("devagent.plugins.subprocess.run", return_value=mock_result):
            result = runner.invoke(app, ["plugins", "install", "no-such-pkg"])
        assert result.exit_code == 1
        assert "Failed" in result.output

    def test_missing_package_arg_exits_nonzero(self):
        result = runner.invoke(app, ["plugins", "install"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_bundle_ep(bundle: PluginBundle):
    ep = MagicMock()
    ep.load.return_value = bundle
    return ep
