from typing import Any, Dict, List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    ORIGINS: List[str] = ["*"]
    SANDBOX_INTERNAL_API_KEY: Optional[str] = None
    RUNTIME_DB_PATH: str = "/tmp/sandbox_runtime.db"
    SEARCH_PROVIDER: str = "duckduckgo"
    BING_SEARCH_API_KEY: Optional[str] = None
    GOOGLE_SEARCH_API_KEY: Optional[str] = None
    GOOGLE_SEARCH_ENGINE_ID: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None
    MCP_CONFIG_PATH: str = "/etc/mcp.json"
    MODEL_NAME: str = "gpt-4o"
    MODEL_PROVIDER: str = "openai"
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000
    API_BASE: Optional[str] = None
    EXTRA_HEADERS: Optional[Dict[str, str]] = None
    BROWSER_ENGINE: str = "playwright"
    AGENT_MODEL_MAX_ITERATIONS: int = 100
    AGENT_MODEL_MAX_RETRIES: int = 3
    AGENT_MODEL_RETRY_INTERVAL_SECONDS: float = 1.0
    AGENT_LOOP_MAX_ROUNDS: int = 40
    AGENT_LOOP_TIMEOUT_SECONDS: int = 1800
    
    # Service timeout settings (minutes)
    SERVICE_TIMEOUT_MINUTES: Optional[int] = None
    
    # Log configuration
    LOG_LEVEL: str = "INFO"
    
    @field_validator("ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if not self.SANDBOX_INTERNAL_API_KEY or not self.SANDBOX_INTERNAL_API_KEY.strip():
            raise ValueError("SANDBOX_INTERNAL_API_KEY is required")
        return self

    @field_validator("EXTRA_HEADERS", mode="before")
    def parse_extra_headers(cls, v: Any) -> Optional[Dict[str, str]]:
        if v is None or v == "":
            return None
        if isinstance(v, dict):
            return {str(k): str(vv) for k, vv in v.items()}
        if isinstance(v, str):
            import json
            parsed = json.loads(v)
            if isinstance(parsed, dict):
                return {str(k): str(vv) for k, vv in parsed.items()}
        raise ValueError("EXTRA_HEADERS must be a JSON object")

    @property
    def model_name(self) -> str:
        return self.MODEL_NAME

    @property
    def model_provider(self) -> str:
        return self.MODEL_PROVIDER

    @property
    def temperature(self) -> float:
        return self.TEMPERATURE

    @property
    def max_tokens(self) -> int:
        return self.MAX_TOKENS

    @property
    def api_base(self) -> Optional[str]:
        return self.API_BASE

    @property
    def extra_headers(self) -> Optional[Dict[str, str]]:
        return self.EXTRA_HEADERS

    @property
    def browser_engine(self) -> str:
        return self.BROWSER_ENGINE


settings = Settings()


def get_settings() -> Settings:
    return settings
