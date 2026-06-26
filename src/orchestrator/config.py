# src/orchestrator/config.py
import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Settings:
    PROJECT_NAME: str = "AI Development Orchestrator"

    # LLM Configuration (OpenAI SDK compatible)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    LLM_MODEL: str = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    # Cost tracking (0 = disabled)
    LLM_BUDGET_LIMIT_USD: float = float(os.getenv("LLM_BUDGET_LIMIT_USD", "0") or "0")

    # Run/Workspace configuration
    RUNS_DIR: str = os.getenv("RUNS_DIR", "output")

    # Guardrail policy configuration
    GUARDRAIL_MODE: str = os.getenv("GUARDRAIL_MODE", "hard_block")  # warn|soft_block|hard_block
    MAX_FILES_TOUCHED: int = int(os.getenv("MAX_FILES_TOUCHED", "25"))
    MAX_LOC_DELTA: int = int(os.getenv("MAX_LOC_DELTA", "800"))

    # Quality thresholds
    MIN_COVERAGE: float = float(os.getenv("MIN_COVERAGE", "80"))
    MIN_PYLINT_SCORE: float = float(os.getenv("MIN_PYLINT_SCORE", "8"))

    # Retry / pipeline
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Default project type for project generation mode
    DEFAULT_PROJECT_TYPE: str = os.getenv("DEFAULT_PROJECT_TYPE", "library")

    @classmethod
    def validate(cls):
        cls.validate_llm()

    @classmethod
    def validate_llm(cls):
        if not cls.LLM_API_KEY:
            from .exceptions import ConfigurationError
            raise ConfigurationError("LLM_API_KEY (or OPENAI_API_KEY) not found in environment variables.")


settings = Settings()
