from typing import Any

from pydantic import BaseModel, Field


class RuntimeRunnerStartRequest(BaseModel):
    session_id: str
    agent_id: str
    user_id: str
    sandbox_id: str
    message: str
    attachments: list[str] = Field(default_factory=list)
    session_status: str
    last_plan: dict[str, Any] | None = None


class RuntimeRunnerEventQuery(BaseModel):
    from_seq: int = Field(default=1, ge=1)
    limit: int = Field(default=200, ge=1, le=1000)
