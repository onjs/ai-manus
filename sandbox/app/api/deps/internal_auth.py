from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_runtime_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    if x_internal_key != settings.SANDBOX_INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

