from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from app.application.services.token_service import TokenService
from app.core.config import Settings, get_settings
from app.infrastructure.repositories.token_state_repository import TokenStateRepository


@lru_cache()
def get_token_service() -> TokenService:
    settings = get_settings()
    repository = TokenStateRepository(
        redis_url=settings.gateway_redis_url,
        key_prefix=settings.gateway_redis_prefix,
    )
    return TokenService(settings=settings, state_repository=repository)


def verify_internal_api_key(
    x_internal_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.gateway_internal_api_key
    if x_internal_key == expected:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def require_scope(required_scope: str):
    async def _dependency(
        authorization: str | None = Header(default=None),
        token_service: TokenService = Depends(get_token_service),
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        token = authorization[len("Bearer ") :].strip()
        result = await token_service.assert_scope(token, required_scope)
        if not result.active:
            if result.reason == "scope_denied":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Scope denied")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inactive")
        return result.claims or {}

    return _dependency
