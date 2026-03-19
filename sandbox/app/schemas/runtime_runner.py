from pydantic import BaseModel, Field


class RuntimeRunnerStartRequest(BaseModel):
    session_id: str
    agent_id: str
    user_id: str
    sandbox_id: str
    message: str


class RuntimeRunnerEventQuery(BaseModel):
    from_seq: int = Field(default=1, ge=1)
    limit: int = Field(default=200, ge=1, le=1000)
