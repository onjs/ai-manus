import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import jwt

from app.core.config import Settings
from app.infrastructure.repositories.token_state_repository import TokenStateRepository
from app.interfaces.schemas.token import (
    TokenIntrospectResponse,
    TokenIssueRequest,
    TokenIssueResponse,
    TokenRevokeRequest,
    TokenRevokeResponse,
)


@dataclass
class TokenValidationResult:
    active: bool
    claims: Optional[dict[str, Any]] = None
    reason: str = ""


class TokenService:
    def __init__(self, settings: Settings, state_repository: TokenStateRepository):
        self._settings = settings
        self._state_repository = state_repository

    def _decode_unverified(self, token: str) -> dict[str, Any]:
        payload = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=[self._settings.gateway_jwt_algorithm],
        )
        if not isinstance(payload, dict):
            raise ValueError("Token payload is invalid")
        return payload

    def _decode_verified(self, token: str) -> dict[str, Any]:
        payload = jwt.decode(
            token,
            self._settings.gateway_token_issuer_secret,
            algorithms=[self._settings.gateway_jwt_algorithm],
            options={"verify_exp": False},
        )
        if not isinstance(payload, dict):
            raise ValueError("Token payload is invalid")
        return payload

    async def issue_token(self, request: TokenIssueRequest) -> TokenIssueResponse:
        now = int(time.time())
        ttl = request.ttl_seconds or self._settings.gateway_token_ttl_seconds
        exp = now + max(1, ttl)
        token_id = uuid.uuid4().hex
        claims: dict[str, Any] = {
            "iss": "ai-manus-gateway",
            "jti": token_id,
            "iat": now,
            "exp": exp,
            "tenant_id": request.tenant_id,
            "session_id": request.session_id,
            "env_id": request.env_id,
            "run_id": request.run_id,
            "agent_id": request.agent_id,
            "scopes": request.scopes,
        }
        token = jwt.encode(
            claims,
            self._settings.gateway_token_issuer_secret,
            algorithm=self._settings.gateway_jwt_algorithm,
        )
        await self._state_repository.set_active(token_id, claims, ttl)
        return TokenIssueResponse(
            token=token,
            token_id=token_id,
            expire_at=exp,
            scopes=request.scopes,
        )

    async def revoke_token(self, request: TokenRevokeRequest) -> TokenRevokeResponse:
        token_id = request.token_id
        claims: Optional[dict[str, Any]] = None
        if request.token:
            try:
                claims = self._decode_unverified(request.token)
                token_id = token_id or str(claims.get("jti"))
            except Exception:
                pass
        if not token_id:
            raise ValueError("token_id or token is required")

        active_claims = await self._state_repository.get_active(token_id)
        if active_claims:
            claims = active_claims
        now = int(time.time())
        exp = int((claims or {}).get("exp", now + self._settings.gateway_token_ttl_seconds))
        ttl = max(1, exp - now)

        await self._state_repository.set_revoked(token_id, request.reason, ttl)
        await self._state_repository.remove_active(token_id)
        return TokenRevokeResponse(revoked=True, token_id=token_id)

    async def introspect_token(
        self,
        *,
        token: Optional[str] = None,
        token_id: Optional[str] = None,
    ) -> TokenIntrospectResponse:
        claims: Optional[dict[str, Any]] = None
        if token:
            try:
                claims = self._decode_verified(token)
                token_id = token_id or str(claims.get("jti"))
            except Exception:
                return TokenIntrospectResponse(active=False, revoked=False, claims=None)
        if not token_id:
            raise ValueError("token_id or token is required")

        revoked = await self._state_repository.get_revoked(token_id)
        if revoked:
            expire_at = int((claims or {}).get("exp")) if claims and claims.get("exp") else None
            return TokenIntrospectResponse(
                active=False,
                revoked=True,
                expire_at=expire_at,
                claims=claims,
            )

        active_claims = await self._state_repository.get_active(token_id)
        claims = claims or active_claims
        if not claims:
            return TokenIntrospectResponse(active=False, revoked=False, claims=None)

        now = int(time.time())
        exp = int(claims.get("exp", 0))
        if exp <= now:
            return TokenIntrospectResponse(active=False, revoked=False, expire_at=exp, claims=claims)

        return TokenIntrospectResponse(
            active=True,
            revoked=False,
            expire_at=exp,
            claims=claims,
        )

    async def assert_scope(self, token: str, required_scope: str) -> TokenValidationResult:
        introspected = await self.introspect_token(token=token)
        if not introspected.active or not introspected.claims:
            return TokenValidationResult(active=False, reason="token_inactive")
        scopes = introspected.claims.get("scopes") or []
        if required_scope not in scopes:
            return TokenValidationResult(active=False, claims=introspected.claims, reason="scope_denied")
        return TokenValidationResult(active=True, claims=introspected.claims)
