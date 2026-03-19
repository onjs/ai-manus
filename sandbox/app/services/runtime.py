import time
from typing import Any

from app.core.config import settings
from app.schemas.runtime import RuntimeGatewayConfigRequest
from app.services.runtime_store import runtime_store


class RuntimeService:
    """Gateway credential store and model config provider for sandbox runtime."""

    def __init__(self):
        self._store = runtime_store

    async def configure_gateway(self, request: RuntimeGatewayConfigRequest) -> dict[str, Any]:
        self._store.set_gateway_credential(
            session_id=request.session_id,
            gateway_base_url=request.gateway_base_url.rstrip("/"),
            gateway_token=request.gateway_token,
            gateway_token_id=request.gateway_token_id,
            gateway_token_expire_at=request.gateway_token_expire_at,
            scopes=request.scopes,
        )
        return {
            "session_id": request.session_id,
            "configured": True,
            "expire_at": request.gateway_token_expire_at,
        }

    async def clear_gateway(self, session_id: str) -> dict[str, Any]:
        existed = self._store.clear_gateway_credential(session_id)
        return {"session_id": session_id, "cleared": existed}

    def has_gateway_config(self, session_id: str) -> bool:
        return self._store.has_gateway_credential(session_id)

    def get_chat_model_kwargs(self, session_id: str) -> dict[str, Any]:
        credential = self._store.get_gateway_credential(session_id)
        if credential is None:
            raise RuntimeError("Gateway runtime is not configured for this session")

        now = int(time.time())
        if int(credential["gateway_token_expire_at"]) <= now:
            self._store.clear_gateway_credential(session_id)
            raise RuntimeError("Gateway token expired")

        return {
            "model": settings.MODEL_NAME,
            "model_provider": settings.MODEL_PROVIDER,
            "temperature": settings.TEMPERATURE,
            "max_tokens": settings.MAX_TOKENS,
            "base_url": f"{str(credential['gateway_base_url']).rstrip('/')}/v1",
            "default_headers": {"Authorization": f"Bearer {credential['gateway_token']}"},
        }


runtime_service = RuntimeService()
