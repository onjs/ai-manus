from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class GatewayStreamEvent:
    event: str
    data: Dict[str, Any]


@dataclass
class GatewayIssuedToken:
    token: str
    token_id: str
    expire_at: int
    scopes: list[str]


class GatewayClient:
    """HTTP client for gateway agent runtime stream APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout_seconds: float = 300.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout=timeout_seconds)

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    def _internal_headers(self) -> Dict[str, str]:
        headers = self._headers()
        if self._api_key:
            headers["X-Internal-Key"] = self._api_key
        return headers

    async def _issue_token(
        self,
        client: httpx.AsyncClient,
        *,
        session_id: str,
        agent_id: str,
        sandbox_id: str,
        scopes: Optional[list[str]] = None,
    ) -> GatewayIssuedToken:
        payload = {
            "tenant_id": "default",
            "session_id": session_id,
            "env_id": sandbox_id,
            "run_id": session_id,
            "agent_id": agent_id,
            "scopes": scopes or ["llm:stream"],
        }
        response = await client.post(
            f"{self._base_url}/v1/token/issue",
            headers=self._internal_headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        token = data.get("token")
        token_id = data.get("token_id")
        expire_at = data.get("expire_at")
        scopes_data = data.get("scopes")
        if not token or not token_id or not isinstance(expire_at, int):
            raise RuntimeError(f"Gateway token issue response invalid: {response.text}")
        if not isinstance(scopes_data, list):
            scopes_data = scopes or ["llm:stream"]
        return GatewayIssuedToken(
            token=token,
            token_id=token_id,
            expire_at=expire_at,
            scopes=[str(s) for s in scopes_data],
        )

    async def _revoke_token(
        self,
        client: httpx.AsyncClient,
        token_id: Optional[str],
        reason: str,
    ) -> None:
        if not token_id:
            return
        response = await client.post(
            f"{self._base_url}/v1/token/revoke",
            headers=self._internal_headers(),
            json={"token_id": token_id, "reason": reason},
        )
        response.raise_for_status()

    async def issue_token(
        self,
        *,
        session_id: str,
        agent_id: str,
        sandbox_id: str,
        scopes: Optional[list[str]] = None,
    ) -> GatewayIssuedToken:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._issue_token(
                client,
                session_id=session_id,
                agent_id=agent_id,
                sandbox_id=sandbox_id,
                scopes=scopes,
            )

    async def revoke_token(self, token_id: Optional[str], reason: str = "revoked") -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await self._revoke_token(client, token_id, reason)
