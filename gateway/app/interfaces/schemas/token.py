from typing import Any, Optional

from pydantic import BaseModel, Field


class TokenIssueRequest(BaseModel):
    tenant_id: str = "default"
    session_id: str
    env_id: str
    run_id: str
    agent_id: str
    scopes: list[str] = Field(default_factory=lambda: ["llm:stream"])
    ttl_seconds: Optional[int] = None


class TokenIssueResponse(BaseModel):
    token: str
    token_id: str
    expire_at: int
    scopes: list[str]


class TokenRevokeRequest(BaseModel):
    token_id: Optional[str] = None
    token: Optional[str] = None
    reason: str = "revoked"


class TokenRevokeResponse(BaseModel):
    revoked: bool
    token_id: str


class TokenIntrospectRequest(BaseModel):
    token_id: Optional[str] = None
    token: Optional[str] = None


class TokenIntrospectResponse(BaseModel):
    active: bool
    revoked: bool
    expire_at: Optional[int] = None
    claims: Optional[dict[str, Any]] = None
