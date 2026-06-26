"""Factory for creating LLM client instances."""

from typing import Optional

from .base import BaseLLMClient
from .cost_tracker import CostTracker
from .openai_client import OpenAIClient


def create_llm_client(
    cost_tracker: Optional[CostTracker] = None,
) -> BaseLLMClient:
    """Create an LLM client based on configuration.

    Args:
        cost_tracker: Optional CostTracker to attach for usage monitoring.

    Returns:
        Configured BaseLLMClient instance.
    """
    client = OpenAIClient()

    if cost_tracker is not None:
        client.set_cost_tracker(cost_tracker)

    return client
