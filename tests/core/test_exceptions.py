"""Tests for the exception hierarchy."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orchestrator.exceptions import (
    AgentError,
    ConfigurationError,
    FileManagerError,
    GuardrailViolation,
    LLMError,
    LLMResponseParseError,
    OrchestratorError,
    WorkflowError,
)


def test_all_exceptions_inherit_from_base():
    """All custom exceptions must inherit from OrchestratorError."""
    assert issubclass(ConfigurationError, OrchestratorError)
    assert issubclass(LLMError, OrchestratorError)
    assert issubclass(LLMResponseParseError, LLMError)
    assert issubclass(WorkflowError, OrchestratorError)
    assert issubclass(AgentError, OrchestratorError)
    assert issubclass(GuardrailViolation, OrchestratorError)
    assert issubclass(FileManagerError, OrchestratorError)


def test_llm_response_parse_error_is_llm_error():
    """LLMResponseParseError should be catchable as LLMError."""
    try:
        raise LLMResponseParseError("bad json")
    except LLMError:
        pass  # Should be caught


def test_exceptions_carry_messages():
    """All exceptions should preserve their error messages."""
    exc = ConfigurationError("missing key")
    assert "missing key" in str(exc)

    exc = LLMError("api timeout")
    assert "api timeout" in str(exc)

    exc = WorkflowError("unknown mode")
    assert "unknown mode" in str(exc)
