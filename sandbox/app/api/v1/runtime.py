from fastapi import APIRouter, Depends, Header, HTTPException, status
from app.core.config import settings
from app.schemas.response import Response
from app.schemas.runtime import RuntimeGatewayConfigRequest
from app.services.runtime import runtime_service

router = APIRouter()


def verify_runtime_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    if x_internal_key != settings.SANDBOX_INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.post("/config", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def configure_gateway_runtime(request: RuntimeGatewayConfigRequest):
    result = await runtime_service.configure_gateway(request)
    return Response(success=True, message="Runtime gateway configured", data=result)


@router.delete("/config/{session_id}", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def clear_gateway_runtime(session_id: str):
    result = await runtime_service.clear_gateway(session_id)
    return Response(success=True, message="Runtime gateway config cleared", data=result)
