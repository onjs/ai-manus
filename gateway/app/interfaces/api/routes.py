from fastapi import APIRouter

from app.interfaces.api import health_routes, internal_token_routes, runtime_routes


def create_api_router() -> APIRouter:
    api_router = APIRouter()
    api_router.include_router(health_routes.router)
    api_router.include_router(internal_token_routes.router)
    api_router.include_router(runtime_routes.router)
    return api_router


router = create_api_router()
