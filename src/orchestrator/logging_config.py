"""Structured logging configuration using Rich handler."""

import logging

from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the orchestrator logger."""
    handler = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        markup=True,
        show_time=False,
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        format="%(message)s",
    )
    return logging.getLogger("orchestrator")


logger = setup_logging()
