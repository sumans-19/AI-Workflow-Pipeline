"""Centralized exception hierarchy for the AI Development Orchestrator."""


class OrchestratorError(Exception):
    """Base exception for all orchestrator errors."""


class ConfigurationError(OrchestratorError):
    """Raised for missing API keys, bad settings, or invalid config."""


class LLMError(OrchestratorError):
    """Raised for API failures, rate limits, or bad LLM responses."""


class LLMResponseParseError(LLMError):
    """Raised when the LLM response cannot be parsed as valid JSON."""


class LLMBudgetExceeded(LLMError):
    """Raised when LLM cost tracking detects spending has exceeded the configured budget."""


class WorkflowError(OrchestratorError):
    """Raised for invalid mode, exhausted retries, or workflow state issues."""


class AgentError(OrchestratorError):
    """Raised when an agent fails during execution."""


class GuardrailViolation(OrchestratorError):
    """Raised when guardrail checks block an unsafe operation."""


class FileManagerError(OrchestratorError):
    """Raised for file I/O failures (read, write, path issues)."""
