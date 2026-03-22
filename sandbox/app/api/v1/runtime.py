from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps.internal_auth import verify_runtime_internal_key
from app.schemas.response import Response
from app.schemas.runtime import RuntimeGatewayConfigRequest
from app.services.runtime import runtime_service
from app.services.runtime_session_id import ensure_valid_session_id

router = APIRouter()


@router.post("/config", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def configure_gateway_runtime(request: RuntimeGatewayConfigRequest):
    try:
        request.session_id = ensure_valid_session_id(request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = await runtime_service.configure_gateway(request)
    return Response(success=True, message="Runtime gateway configured", data=result)


@router.delete("/config/{session_id}", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def clear_gateway_runtime(session_id: str):
    try:
        session_id = ensure_valid_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = await runtime_service.clear_gateway(session_id)
    return Response(success=True, message="Runtime gateway config cleared", data=result)
