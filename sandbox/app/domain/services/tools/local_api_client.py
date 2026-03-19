from __future__ import annotations

from typing import Any

import httpx


class LocalSandboxApiClient:
    """HTTP client for sandbox local APIs (shell/file)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(120.0))

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(path, json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("sandbox local api response must be json object")
        return body


local_sandbox_api_client = LocalSandboxApiClient()
