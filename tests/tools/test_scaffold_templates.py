"""Tests for scaffold templates, git init, and the init CLI command (US-008)."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.scaffold_templates import get_template
from orchestrator.tools.file_manager import FileManager


# ===================================================================
# Template tests
# ===================================================================


class TestLibraryTemplate:
    def test_has_expected_files(self):
        files = get_template("library", "myapp")
        expected = [
            "src/myapp/__init__.py",
            "src/myapp/__main__.py",
            "tests/__init__.py",
            "tests/conftest.py",
            "tests/test_myapp.py",
            "pyproject.toml",
            "requirements.txt",
            ".gitignore",
            ".env.example",
            "README.md",
        ]
        for path in expected:
            assert path in files, f"Missing file: {path}"

    def test_pyproject_has_name(self):
        files = get_template("library", "my-app")
        assert 'name = "my-app"' in files["pyproject.toml"]


class TestFastAPITemplate:
    def test_has_expected_files(self):
        files = get_template("fastapi", "myapi")
        expected = [
            "src/myapi/__init__.py",
            "src/myapi/main.py",
            "src/myapi/routers/__init__.py",
            "src/myapi/models.py",
            "tests/test_main.py",
            "Dockerfile",
            ".gitignore",
            "README.md",
        ]
        for path in expected:
            assert path in files, f"Missing file: {path}"

    def test_main_has_fastapi_app(self):
        files = get_template("fastapi", "myapi")
        assert "FastAPI" in files["src/myapi/main.py"]

    def test_dockerfile_references_package(self):
        files = get_template("fastapi", "myapi")
        assert "myapi.main:app" in files["Dockerfile"]


class TestFlaskTemplate:
    def test_has_expected_files(self):
        files = get_template("flask", "webapp")
        expected = [
            "src/webapp/__init__.py",
            "src/webapp/app.py",
            "tests/test_app.py",
            ".gitignore",
            "README.md",
        ]
        for path in expected:
            assert path in files, f"Missing file: {path}"

    def test_app_has_flask_factory(self):
        files = get_template("flask", "webapp")
        assert "create_app" in files["src/webapp/app.py"]
        assert "Flask" in files["src/webapp/app.py"]


class TestCLITemplate:
    def test_has_expected_files(self):
        files = get_template("cli", "mycli")
        expected = [
            "src/mycli/__init__.py",
            "src/mycli/cli.py",
            "tests/test_cli.py",
            ".gitignore",
            "README.md",
        ]
        for path in expected:
            assert path in files, f"Missing file: {path}"

    def test_cli_has_argparse(self):
        files = get_template("cli", "mycli")
        assert "argparse" in files["src/mycli/cli.py"]


class TestScriptTemplate:
    def test_has_expected_files(self):
        files = get_template("script", "myscript")
        expected = ["main.py", "tests/test_main.py", ".gitignore", "README.md"]
        for path in expected:
            assert path in files, f"Missing file: {path}"

    def test_minimal_structure(self):
        files = get_template("script", "myscript")
        assert "src/" not in str(files.keys())


class TestTemplateNameSubstitution:
    def test_hyphens_converted_to_underscores(self):
        files = get_template("library", "my-cool-app")
        assert "src/my_cool_app/__init__.py" in files

    def test_spaces_converted_to_underscores(self):
        files = get_template("library", "my cool app")
        assert "src/my_cool_app/__init__.py" in files

    def test_readme_has_project_name(self):
        files = get_template("library", "myapp")
        assert "# myapp" in files["README.md"]

    def test_uppercase_converted_to_lowercase(self):
        files = get_template("library", "MyApp")
        assert "src/myapp/__init__.py" in files


class TestInvalidTemplate:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown project type"):
            get_template("django", "myapp")


# ===================================================================
# Git init tests
# ===================================================================


class TestGitInit:
    def test_success(self, tmp_path):
        project = tmp_path / "myapp"
        project.mkdir()
        with patch("orchestrator.tools.file_manager.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = FileManager.git_init(str(project))
            assert result is True
            mock_run.assert_called_once_with(
                ["git", "init", str(project)],
                capture_output=True,
                check=True,
            )

    def test_git_not_found(self, tmp_path):
        project = tmp_path / "myapp"
        project.mkdir()
        with patch("orchestrator.tools.file_manager.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            result = FileManager.git_init(str(project))
            assert result is False

    def test_git_fails(self, tmp_path):
        project = tmp_path / "myapp"
        project.mkdir()
        with patch("orchestrator.tools.file_manager.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")
            result = FileManager.git_init(str(project))
            assert result is False


# ===================================================================
# Init command integration tests
# ===================================================================


class TestInitCommand:
    def test_creates_files_on_disk(self, tmp_path):
        template = get_template("library", "testproj")
        project_path = FileManager.create_project_structure(str(tmp_path), "testproj", template)
        assert (tmp_path / "testproj" / "src" / "testproj" / "__init__.py").exists()
        assert (tmp_path / "testproj" / "tests" / "test_testproj.py").exists()
        assert (tmp_path / "testproj" / ".gitignore").exists()
        assert (tmp_path / "testproj" / "README.md").exists()
        assert (tmp_path / "testproj" / "pyproject.toml").exists()

    def test_creates_fastapi_project(self, tmp_path):
        template = get_template("fastapi", "myapi")
        project_path = FileManager.create_project_structure(str(tmp_path), "myapi", template)
        assert (tmp_path / "myapi" / "src" / "myapi" / "main.py").exists()
        assert (tmp_path / "myapi" / "Dockerfile").exists()

    def test_file_contents_are_valid(self, tmp_path):
        template = get_template("library", "myapp")
        FileManager.create_project_structure(str(tmp_path), "myapp", template)
        init_content = (tmp_path / "myapp" / "src" / "myapp" / "__init__.py").read_text()
        assert "myapp package" in init_content

    def test_tree_display(self, tmp_path):
        template = get_template("library", "myapp")
        project_path = FileManager.create_project_structure(str(tmp_path), "myapp", template)
        tree = FileManager.build_project_tree(project_path)
        assert "myapp/" in tree
        assert "src" in tree
        assert "tests" in tree
