from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class UpstreamProviderError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = detail


class BaseLLMProvider(ABC):
    @abstractmethod
    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def stream_chat_completion(self, payload: dict[str, Any]) -> AsyncGenerator[bytes, None]:
        ...
