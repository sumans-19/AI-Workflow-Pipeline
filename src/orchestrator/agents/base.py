from abc import ABC, abstractmethod

from ..core.context import WorkflowContext


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def execute(self, context: WorkflowContext) -> WorkflowContext:
        """Process the context and return the updated context."""
        ...
