"""Tests for FileManager project structure capabilities."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orchestrator.tools.file_manager import FileManager


def test_create_project_structure():
    """FileManager should create a full project directory with all files."""
    fm = FileManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        files = {
            "src/myapp/__init__.py": "# init",
            "src/myapp/main.py": "def main(): pass",
            "tests/__init__.py": "",
            "tests/test_main.py": "def test_main(): pass",
            "requirements.txt": "pytest",
            "README.md": "# myapp",
        }

        root = fm.create_project_structure(tmpdir, "myapp", files)

        assert os.path.isdir(os.path.join(root, "src", "myapp"))
        assert os.path.isdir(os.path.join(root, "tests"))
        assert os.path.isfile(os.path.join(root, "src", "myapp", "__init__.py"))
        assert os.path.isfile(os.path.join(root, "src", "myapp", "main.py"))
        assert os.path.isfile(os.path.join(root, "requirements.txt"))
        assert os.path.isfile(os.path.join(root, "README.md"))


def test_build_project_tree():
    """FileManager should produce a readable tree string."""
    fm = FileManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        files = {
            "src/app.py": "code",
            "tests/test_app.py": "test",
            "README.md": "# test",
        }
        root = fm.create_project_structure(tmpdir, "proj", files)
        tree = fm.build_project_tree(root)

        assert "proj/" in tree
        assert "src" in tree
        assert "app.py" in tree
        assert "tests" in tree
        assert "README.md" in tree


def test_build_project_tree_nonexistent():
    """build_project_tree should handle non-existent directories."""
    fm = FileManager()
    tree = fm.build_project_tree("/nonexistent/path")
    assert "not found" in tree


def test_write_and_read_file():
    """Basic write and read roundtrip."""
    fm = FileManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = fm.write_file("test.py", "print('hello')", directory=tmpdir)
        assert os.path.isfile(path)
        content = fm.read_file(path)
        assert content == "print('hello')"


def test_write_json():
    """write_json should produce valid JSON."""
    import json
    fm = FileManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        data = {"key": "value", "nums": [1, 2, 3]}
        path = fm.write_json("data.json", data, tmpdir)
        assert os.path.isfile(path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == data


def test_ensure_run_dirs():
    """ensure_run_dirs should create all required subdirectories."""
    fm = FileManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = fm.ensure_run_dirs(tmpdir, "test-run-123")
        assert os.path.isdir(paths["run_root"])
        assert os.path.isdir(paths["workspace"])
        assert os.path.isdir(paths["artifacts"])
        assert os.path.isdir(paths["metrics"])
        assert os.path.isdir(paths["logs"])
def test_build_project_tree_depth_limit():
    """build_project_tree should respect max_depth."""
    fm = FileManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a deep structure: a/b/c/d/e/f
        path = Path(tmpdir) / "a" / "b" / "c" / "d" / "e" / "f"
        path.mkdir(parents=True)
        (path / "file.txt").touch()
        
        # depth 2 should only show up to a/b
        tree = fm.build_project_tree(tmpdir, max_depth=2)
        assert "a" in tree
        assert "b" in tree
        assert "`-- c" not in tree
        assert "|-- c" not in tree
        assert "file.txt" not in tree
