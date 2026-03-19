from app.domain.models.event import BaseEvent
from typing import AsyncGenerator
from abc import ABC, abstractmethod

class BaseFlow(ABC):

    @abstractmethod
    def run(self) -> AsyncGenerator[BaseEvent, None]:
        pass

    @abstractmethod
    def is_done(self) -> bool:
        pass
