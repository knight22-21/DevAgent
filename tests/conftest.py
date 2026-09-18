from pathlib import Path

import pytest


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a sample Python project structure for testing."""
    project = tmp_path / "sample_project"
    project.mkdir()
    
    # Create a gitignore
    (project / ".gitignore").write_text("node_modules/\n.venv/\n__pycache__/\n")
    
    # Create main app file
    app_py = project / "app.py"
    app_py.write_text(
        "def main():\n"
        "    print('Hello World')\n\n"
        "class AppServer:\n"
        "    def run(self):\n"
        "        pass\n"
    )
    
    # Create an ignored file
    venv_dir = project / ".venv"
    venv_dir.mkdir()
    (venv_dir / "ignored.py").write_text("def ignored(): pass")
    
    # Create a non-python file
    (project / "README.md").write_text("# Sample Project\nThis is a sample project.")
    
    return project

@pytest.fixture
def mock_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mock the config path to use a temporary file."""
    config_file = tmp_path / "config.toml"
    monkeypatch.setenv("SPECSYNC_CONFIG_PATH", str(config_file))
    return config_file


# ---------------------------------------------------------------------------
# F3 — Watcher fixtures
# ---------------------------------------------------------------------------

from datetime import UTC
from unittest.mock import patch

import pytest_asyncio


@pytest_asyncio.fixture
async def watcher_db(tmp_path: Path):
    """Provides a temporary watcher database for tests."""
    db_path = tmp_path / "watcher.db"
    with patch("devagent.watcher.storage._db_path", return_value=db_path):
        from devagent.watcher.storage import init_watcher_db
        await init_watcher_db()
        yield db_path


@pytest.fixture
def sample_watcher_analysis():
    from datetime import datetime

    from devagent.core.models import IssueComplexity, WatcherAnalysis
    return WatcherAnalysis(
        owner="myorg",
        repo="backend",
        issue_number=142,
        issue_title="Add OAuth2 login with Google",
        issue_url="https://github.com/myorg/backend/issues/142",
        analysed_at=datetime.now(UTC),
        requirements_count=4,
        conflicts_count=1,
        complexity=IssueComplexity.MEDIUM,
        touched_files=["auth/session.py", "auth/routes.py", "models/user.py"],
        conflicted_files=["auth/session.py"],
        requirement_summaries=[],
        full_report_available=False,
    )

