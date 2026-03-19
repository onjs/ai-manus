from fastapi import APIRouter

from app.core.config import get_settings
from app.interfaces.schemas.response import APIResponse

router = APIRouter(prefix="/v1/gateway", tags=["gateway"])


@router.get("/health", response_model=APIResponse[dict])
async def health() -> APIResponse[dict]:
    return APIResponse(data={"status": "ok"})


@router.get("/ready", response_model=APIResponse[dict])
async def ready() -> APIResponse[dict]:
    return APIResponse(data={"ready": True})


@router.get("/config/hash", response_model=APIResponse[dict])
async def config_hash() -> APIResponse[dict]:
    settings = get_settings()
    route_hash = hash((settings.api_base, settings.model_provider, settings.model_name))
    return APIResponse(data={"route_hash": str(route_hash), "policy_hash": "default"})
