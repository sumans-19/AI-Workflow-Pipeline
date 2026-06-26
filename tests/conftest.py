"""Shared test fixtures for the AI Development Orchestrator test suite."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def temp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_llm():
    """Provide a mock LLM client that returns predefined responses."""
    client = MagicMock()
    client.generate.return_value = '{"files": [{"path": "main.py", "source_code": "def hello():\\n    return \\"world\\"\\n"}]}'
    return client


@pytest.fixture
def sample_context(temp_dir):
    """Provide a sample WorkflowContext for testing."""
    from orchestrator.core.context import WorkflowContext
    context = WorkflowContext(
        requirements="A simple hello world module",
        mode="GENERATE",
    )
    context.workspace_path = temp_dir
    context.artifacts_path = os.path.join(temp_dir, "artifacts")
    context.metrics_path = os.path.join(temp_dir, "metrics")
    context.logs_path = os.path.join(temp_dir, "logs")
    os.makedirs(context.artifacts_path, exist_ok=True)
    os.makedirs(context.metrics_path, exist_ok=True)
    return context


@pytest.fixture
def sample_source_code():
    """Provide sample source code for testing."""
    return {
        "calculator.py": '''"""Simple calculator module."""


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divide a by b.

    Raises:
        ValueError: If b is zero.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
''',
    }


@pytest.fixture
def sample_project_source_code():
    """Provide sample multi-file source code for project mode testing."""
    return {
        "src/calculator/__init__.py": '"""Calculator package."""\n\nfrom .operations import add, subtract\n\n__all__ = ["add", "subtract"]\n',
        "src/calculator/operations.py": '"""Calculator operations."""\n\n\ndef add(a: float, b: float) -> float:\n    """Add two numbers."""\n    return a + b\n\n\ndef subtract(a: float, b: float) -> float:\n    """Subtract b from a."""\n    return a - b\n',
        "tests/__init__.py": "",
        "tests/test_operations.py": '"""Tests for calculator operations."""\n\nimport pytest\nfrom calculator.operations import add, subtract\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\ndef test_subtract():\n    assert subtract(5, 3) == 2\n',
        "requirements.txt": "pytest>=9.0\n",
        "pyproject.toml": '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "calculator"\nversion = "0.1.0"\n',
        "README.md": "# Calculator\n\nA simple calculator package.\n",
    }


@pytest.fixture
def mock_llm_env(monkeypatch):
    """Set LLM environment variables for testing."""
    from orchestrator.config import Settings
    monkeypatch.setattr(Settings, "LLM_API_KEY", "test-llm-key-12345")
    monkeypatch.setattr(Settings, "LLM_BASE_URL", "https://fake-llm.example.com")
    monkeypatch.setattr(Settings, "LLM_MODEL", "test-model")


@pytest.fixture
def cost_tracker():
    """Provide a fresh CostTracker instance."""
    from orchestrator.llm.cost_tracker import CostTracker
    return CostTracker()
