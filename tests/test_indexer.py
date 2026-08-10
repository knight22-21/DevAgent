import pytest
from pathlib import Path

from devagent.mcp.servers.code_search.indexer import (
    chunk_python_file,
    chunk_generic_file,
    get_gitignore_spec,
    is_ignored
)

def test_python_file_chunking():
    code = (
        "def helper_func():\n"
        "    pass\n"
        "\n"
        "class MyClass:\n"
        "    def my_method(self):\n"
        "        print('hello')\n"
        "\n"
        "    def another_method(self):\n"
        "        pass\n"
    )
    
    chunks = chunk_python_file("test.py", code)
    
    assert len(chunks) == 4  # Class, method1, method2, helper_func
    
    # Check types
    types = set(c.chunk_type for c in chunks)
    assert "class" in types
    assert "function" in types
    
    # Check names
    names = set(c.name for c in chunks)
    assert "helper_func" in names
    assert "MyClass" in names
    assert "MyClass.my_method" in names
    assert "MyClass.another_method" in names

def test_generic_file_chunking():
    text = "Line 1\n" * 100
    chunks = chunk_generic_file("test.txt", text)

    assert len(chunks) > 0
    assert chunks[0].chunk_type == "file"
    assert chunks[0].name == "test.txt"

def test_gitignore_respected(temp_project_dir: Path):
    spec = get_gitignore_spec(temp_project_dir)
    
    # Ignored by .gitignore
    assert is_ignored(temp_project_dir / "node_modules" / "test.js", temp_project_dir, spec)
    assert is_ignored(temp_project_dir / ".venv" / "lib.py", temp_project_dir, spec)
    assert is_ignored(temp_project_dir / "__pycache__" / "app.cpython-312.pyc", temp_project_dir, spec)
    
    # Not ignored
    assert not is_ignored(temp_project_dir / "app.py", temp_project_dir, spec)
    assert not is_ignored(temp_project_dir / "README.md", temp_project_dir, spec)
    
    # Binary extensions ignored
    assert is_ignored(temp_project_dir / "image.png", temp_project_dir, spec)
