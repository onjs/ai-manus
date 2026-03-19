from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import trace_id_middleware
from app.interfaces.api.routes import router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.middleware("http")(trace_id_middleware)
app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "status": "ok"}
