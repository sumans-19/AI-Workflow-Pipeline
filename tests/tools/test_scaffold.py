"""Tests for the ProjectScaffold data model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orchestrator.core.scaffold import GeneratedFile, ProjectScaffold, ProjectType


def test_project_type_values():
    assert ProjectType.FASTAPI_APP.value == "fastapi"
    assert ProjectType.FLASK_APP.value == "flask"
    assert ProjectType.CLI_TOOL.value == "cli"
    assert ProjectType.LIBRARY.value == "library"
    assert ProjectType.SCRIPT.value == "script"


def test_scaffold_add_file():
    scaffold = ProjectScaffold(name="myapp")
    scaffold.add_file("src/myapp/main.py", "print('hello')")
    assert len(scaffold.files) == 1
    assert scaffold.files[0].path == "src/myapp/main.py"
    assert scaffold.files[0].content == "print('hello')"


def test_scaffold_get_source_files():
    scaffold = ProjectScaffold(name="myapp")
    scaffold.add_file("src/myapp/main.py", "code", is_test=False, is_config=False)
    scaffold.add_file("tests/test_main.py", "tests", is_test=True)
    scaffold.add_file("pyproject.toml", "config", is_config=True)

    sources = scaffold.get_source_files()
    assert len(sources) == 1
    assert sources[0].path == "src/myapp/main.py"


def test_scaffold_get_test_files():
    scaffold = ProjectScaffold(name="myapp")
    scaffold.add_file("src/myapp/main.py", "code")
    scaffold.add_file("tests/test_main.py", "tests", is_test=True)

    tests = scaffold.get_test_files()
    assert len(tests) == 1
    assert tests[0].path == "tests/test_main.py"


def test_scaffold_to_source_code_dict():
    scaffold = ProjectScaffold(name="myapp")
    scaffold.add_file("src/a.py", "code_a")
    scaffold.add_file("src/b.py", "code_b")

    d = scaffold.to_source_code_dict()
    assert d == {"src/a.py": "code_a", "src/b.py": "code_b"}


def test_from_source_code():
    source = {
        "src/app.py": "code",
        "tests/test_app.py": "test code",
        "pyproject.toml": "config",
        "requirements.txt": "pytest",
    }
    scaffold = ProjectScaffold.from_source_code(source, "myapp", "library")
    assert scaffold.name == "myapp"
    assert len(scaffold.files) == 4

    # Check classification
    test_files = scaffold.get_test_files()
    assert len(test_files) == 1
    assert test_files[0].path == "tests/test_app.py"

    config_files = scaffold.get_config_files()
    assert len(config_files) == 2
