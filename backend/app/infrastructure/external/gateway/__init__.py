from functools import lru_cache
from app.core.config import get_settings
from app.infrastructure.external.gateway.client import GatewayClient


@lru_cache()
def get_gateway_client() -> GatewayClient:
    settings = get_settings()
    return GatewayClient(
        base_url=settings.gateway_base_url or "",
        api_key=settings.gateway_api_key,
        timeout_seconds=settings.gateway_timeout_seconds,
    )
