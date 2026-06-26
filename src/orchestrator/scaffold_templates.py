"""Static project templates for the `init` command (no LLM calls)."""

from typing import Dict

_GITIGNORE = """\
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Distribution / packaging
dist/
build/
*.egg-info/
*.egg

# Virtual environments
.venv/
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment
.env

# Testing
.pytest_cache/
.coverage
htmlcov/
.ruff_cache/

# OS
.DS_Store
Thumbs.db
"""

_PYPROJECT = """\
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{project_name}"
version = "0.1.0"
description = ""
requires-python = ">=3.10"

[tool.pytest.ini_options]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py310"
"""

_ENV_EXAMPLE = """\
# Copy this file to .env and fill in your real values
"""


def _readme(project_name: str) -> str:
    return f"""\
# {project_name}

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
```

## Run Tests

```bash
pytest
```
"""


def get_template(project_type: str, project_name: str) -> Dict[str, str]:
    """Return file path -> content mapping for the given project type.

    Args:
        project_type: One of "library", "fastapi", "flask", "cli", "script".
        project_name: Project name (used for directory and package naming).

    Returns:
        Dict mapping relative file paths to their content.
    """
    pkg = project_name.replace("-", "_").replace(" ", "_").lower()
    generators = {
        "library": _library,
        "fastapi": _fastapi,
        "flask": _flask,
        "cli": _cli,
        "script": _script,
    }
    gen = generators.get(project_type)
    if gen is None:
        raise ValueError(
            f"Unknown project type: {project_type!r}. "
            f"Choose from: {', '.join(generators)}"
        )
    files = gen(project_name, pkg)
    files[".gitignore"] = _GITIGNORE
    files[".env.example"] = _ENV_EXAMPLE
    files["README.md"] = _readme(project_name)
    return files


def _library(name: str, pkg: str) -> Dict[str, str]:
    return {
        f"src/{pkg}/__init__.py": f'"""{name} package."""\n',
        f"src/{pkg}/__main__.py": f'"""Entry point for `python -m {pkg}`."""\n\n\ndef main():\n    print("Hello from {name}!")\n\n\nif __name__ == "__main__":\n    main()\n',
        "tests/__init__.py": "",
        "tests/conftest.py": f"""\
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
""",
        f"tests/test_{pkg}.py": f'''\
"""Tests for {name}."""\n\n\ndef test_import():
    import {pkg}
    assert {pkg} is not None
''',
        "pyproject.toml": _PYPROJECT.format(project_name=name),
        "requirements.txt": "pytest>=8.0\n",
    }


def _fastapi(name: str, pkg: str) -> Dict[str, str]:
    return {
        f"src/{pkg}/__init__.py": f'"""{name} — FastAPI application."""\n',
        f"src/{pkg}/main.py": f"""\
\"\"\"FastAPI application entry point.\"\"\"

from fastapi import FastAPI

app = FastAPI(title="{name}", version="0.1.0")


@app.get("/health")
def health():
    return {{"status": "ok"}}
""",
        f"src/{pkg}/routers/__init__.py": "",
        f"src/{pkg}/models.py": f'"""Data models for {name}."""\n',
        "tests/__init__.py": "",
        "tests/conftest.py": f"""\
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from {pkg}.main import app


@pytest.fixture
def client():
    return TestClient(app)
""",
        "tests/test_main.py": f"""\
\"\"\"Tests for the FastAPI application.\"\"\"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {{"status": "ok"}}
""",
        "pyproject.toml": _PYPROJECT.format(project_name=name),
        "requirements.txt": "fastapi>=0.110\nuvicorn>=0.29\npytest>=8.0\nhttpx>=0.27\n",
        "Dockerfile": f"""\
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install -e .

EXPOSE 8000
CMD ["uvicorn", "{pkg}.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    }


def _flask(name: str, pkg: str) -> Dict[str, str]:
    return {
        f"src/{pkg}/__init__.py": f'"""{name} — Flask application."""\n',
        f"src/{pkg}/app.py": f"""\
\"\"\"Flask application factory.\"\"\"

from flask import Flask, jsonify


def create_app():
    app = Flask(__name__)

    @app.route("/health")
    def health():
        return jsonify({{"status": "ok"}})

    return app
""",
        "tests/__init__.py": "",
        "tests/conftest.py": f"""\
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from {pkg}.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()
""",
        "tests/test_app.py": f"""\
\"\"\"Tests for the Flask application.\"\"\"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {{"status": "ok"}}
""",
        "pyproject.toml": _PYPROJECT.format(project_name=name),
        "requirements.txt": "flask>=3.0\npytest>=8.0\n",
    }


def _cli(name: str, pkg: str) -> Dict[str, str]:
    return {
        f"src/{pkg}/__init__.py": f'"""{name} — CLI tool."""\n',
        f"src/{pkg}/cli.py": f"""\
\"\"\"Command-line interface for {name}.\"\"\"

import argparse


def main():
    parser = argparse.ArgumentParser(prog="{name}", description="{name} CLI tool")
    parser.add_argument("command", help="Command to run")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        print(f"Running: {{args.command}}")


if __name__ == "__main__":
    main()
""",
        "tests/__init__.py": "",
        "tests/conftest.py": f"""\
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
""",
        f"tests/test_cli.py": f"""\
\"\"\"Tests for {name} CLI.\"\"\"


def test_import():
    from {pkg}.cli import main
    assert callable(main)
""",
        "pyproject.toml": _PYPROJECT.format(project_name=name),
        "requirements.txt": "pytest>=8.0\n",
    }


def _script(name: str, pkg: str) -> Dict[str, str]:
    return {
        "main.py": f'"""{name} — standalone script."""\n\n\ndef main():\n    print("Hello from {name}!")\n\n\nif __name__ == "__main__":\n    main()\n',
        "tests/test_main.py": f"""\
\"\"\"Tests for {name} script.\"\"\"


def test_main():
    from main import main
    # Smoke test — just verify it\\'s callable
    assert callable(main)
""",
        "pyproject.toml": _PYPROJECT.format(project_name=name),
        "requirements.txt": "pytest>=8.0\n",
    }
