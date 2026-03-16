import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OpenFangStreamEvent:
    event: str
    data: Dict[str, Any]


class OpenFangClient:
    """Thin HTTP client for OpenFang agent APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        default_template: str = "assistant",
        timeout_seconds: float = 300.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_template = default_template
        self._timeout = httpx.Timeout(timeout=timeout_seconds)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def list_agents(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/api/agents",
                headers=self._headers(),
            )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    async def spawn_agent(self, name: str) -> str:
        payload = {
            "manifest_toml": "",
            "template": self._default_template,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/agents",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                # Fallback to a minimal inline manifest when template is unavailable.
                fallback_manifest = f"""
name = "{name}"
version = "0.1.0"
description = "ai-manus openfang bridge agent"
author = "ai-manus"
module = "builtin:chat"

[model]
provider = "openai"
model = "gpt-4o-mini"

[capabilities]
tools = []
memory_read = ["*"]
memory_write = ["self.*"]
""".strip()
                response = await client.post(
                    f"{self._base_url}/api/agents",
                    headers=self._headers(),
                    json={"manifest_toml": fallback_manifest},
                )
        response.raise_for_status()
        data = response.json()
        agent_id = data.get("agent_id")
        if not agent_id:
            raise RuntimeError(f"OpenFang spawn response missing agent_id: {data}")
        return agent_id

    async def ensure_agent(self, configured_agent_id: Optional[str], name: str) -> str:
        if configured_agent_id:
            return configured_agent_id

        try:
            return await self.spawn_agent(name)
        except Exception as spawn_error:
            logger.warning(
                "Failed to spawn OpenFang agent, trying existing agent list: %s",
                spawn_error,
            )

        agents = await self.list_agents()
        if not agents:
            raise RuntimeError(
                "No OpenFang agents available and auto-spawn failed. "
                "Please start OpenFang and create at least one agent."
            )
        return str(agents[0]["id"])

    async def stream_message(
        self,
        agent_id: str,
        message: str,
    ) -> AsyncGenerator[OpenFangStreamEvent, None]:
        url = f"{self._base_url}/api/agents/{agent_id}/message/stream"
        payload = {"message": message}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="ignore")
                    raise RuntimeError(
                        f"OpenFang stream request failed: {response.status_code}, {detail}"
                    )

                event_name: Optional[str] = None
                data_lines: list[str] = []

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        if not event_name and not data_lines:
                            continue
                        data_str = "\n".join(data_lines).strip()
                        payload_data: Dict[str, Any] = {}
                        if data_str:
                            try:
                                parsed = json.loads(data_str)
                                if isinstance(parsed, dict):
                                    payload_data = parsed
                                else:
                                    payload_data = {"value": parsed}
                            except json.JSONDecodeError:
                                payload_data = {"raw": data_str}
                        yield OpenFangStreamEvent(
                            event=event_name or "chunk",
                            data=payload_data,
                        )
                        event_name = None
                        data_lines = []
                        continue

                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        event_name = line[len("event:"):].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[len("data:"):].strip())

                if event_name or data_lines:
                    data_str = "\n".join(data_lines).strip()
                    payload_data = {}
                    if data_str:
                        try:
                            parsed = json.loads(data_str)
                            payload_data = parsed if isinstance(parsed, dict) else {"value": parsed}
                        except json.JSONDecodeError:
                            payload_data = {"raw": data_str}
                    yield OpenFangStreamEvent(
                        event=event_name or "chunk",
                        data=payload_data,
                    )
