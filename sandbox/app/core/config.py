from typing import List, Optional, Union
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
    BROWSER_ENGINE_VISION_ENABLED: bool = True
    BROWSER_ENGINE_VISION_MAX_IMAGE_BYTES: int = 350000
    BROWSER_ENGINE_VISION_ROUND_LIMIT: int = 6
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


settings = Settings() 
