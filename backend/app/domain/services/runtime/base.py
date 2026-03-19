from abc import ABC, abstractmethod

from app.domain.external.task import Task
from app.domain.models.session import Session


class AgentRuntime(ABC):
    """Runtime boundary for creating executable session tasks."""

    @abstractmethod
    async def create_task(self, session: Session) -> Task:
        """Create a runnable task for the given session."""
        ...
