from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class BaseLLMProvider(ABC):
    @abstractmethod
    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def stream_chat_completion(self, payload: dict[str, Any]) -> AsyncGenerator[bytes, None]:
        ...
