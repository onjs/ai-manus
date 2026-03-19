from typing import Any, AsyncGenerator, Dict

import httpx

from app.infrastructure.providers.base_provider import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(
        self,
        api_base: str,
        api_key: str | None,
        model_name: str,
        timeout_seconds: float = 120.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._timeout = httpx.Timeout(timeout=timeout_seconds)
        self._extra_headers = extra_headers or {}

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        for key, value in self._extra_headers.items():
            headers[str(key)] = str(value)
        return headers

    def _build_payload(self, payload: dict[str, Any], force_stream: bool | None = None) -> dict[str, Any]:
        request_payload = dict(payload)
        if not request_payload.get("model"):
            request_payload["model"] = self._model_name
        if force_stream is not None:
            request_payload["stream"] = force_stream
        return request_payload

    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._api_base}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                headers=self._headers(),
                json=self._build_payload(payload, force_stream=False),
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("upstream chat completions response must be JSON object")
            return body

    async def stream_chat_completion(self, payload: dict[str, Any]) -> AsyncGenerator[bytes, None]:
        url = f"{self._api_base}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=self._build_payload(payload, force_stream=True),
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_raw():
                    if not chunk:
                        continue
                    yield chunk
