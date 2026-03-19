from pydantic import BaseModel, Field


class RuntimeGatewayConfigRequest(BaseModel):
    session_id: str
    gateway_base_url: str
    gateway_token: str
    gateway_token_id: str
    gateway_token_expire_at: int
    scopes: list[str] = Field(default_factory=lambda: ["llm:stream"])
