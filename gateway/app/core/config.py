from functools import lru_cache
import json
import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_extra_headers() -> dict | None:
    raw = os.environ.get("EXTRA_HEADERS")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


class Settings(BaseSettings):
    app_name: str = "ai-manus-gateway"
    app_env: str = "development"
    log_level: str = "INFO"

    gateway_internal_api_key: str | None = None
    gateway_token_issuer_secret: str = "dev-gateway-secret"
    gateway_jwt_algorithm: str = "HS256"
    gateway_token_ttl_seconds: int = 1800
    gateway_redis_url: str | None = None
    gateway_redis_prefix: str = "gw"

    api_key: str | None = None
    api_base: str | None = None
    model_name: str = "gpt-4o-mini"
    model_provider: str = "openai"
    temperature: float = 0.7
    max_tokens: int = 2000
    extra_headers: dict | None = None
    gateway_timeout_seconds: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_required_security(self) -> "Settings":
        if not self.gateway_internal_api_key or not self.gateway_internal_api_key.strip():
            raise ValueError("GATEWAY_INTERNAL_API_KEY is required")
        return self


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.extra_headers = _parse_extra_headers()
    return settings
