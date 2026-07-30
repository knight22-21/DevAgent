import os
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
