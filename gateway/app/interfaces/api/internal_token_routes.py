from fastapi import APIRouter, Depends, HTTPException, status

from app.application.services.token_service import TokenService
from app.core.auth import get_token_service, verify_internal_api_key
from app.interfaces.schemas.response import APIResponse
from app.interfaces.schemas.token import (
    TokenIntrospectRequest,
    TokenIntrospectResponse,
    TokenIssueRequest,
    TokenIssueResponse,
    TokenRevokeRequest,
    TokenRevokeResponse,
)

router = APIRouter(prefix="/v1/token", tags=["token"])


@router.post("/issue", response_model=APIResponse[TokenIssueResponse], dependencies=[Depends(verify_internal_api_key)])
async def issue_token(
    request: TokenIssueRequest,
    token_service: TokenService = Depends(get_token_service),
) -> APIResponse[TokenIssueResponse]:
    data = await token_service.issue_token(request)
    return APIResponse(data=data)


@router.post("/revoke", response_model=APIResponse[TokenRevokeResponse], dependencies=[Depends(verify_internal_api_key)])
async def revoke_token(
    request: TokenRevokeRequest,
    token_service: TokenService = Depends(get_token_service),
) -> APIResponse[TokenRevokeResponse]:
    try:
        data = await token_service.revoke_token(request)
        return APIResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/introspect",
    response_model=APIResponse[TokenIntrospectResponse],
    dependencies=[Depends(verify_internal_api_key)],
)
async def introspect_token(
    request: TokenIntrospectRequest,
    token_service: TokenService = Depends(get_token_service),
) -> APIResponse[TokenIntrospectResponse]:
    try:
        data = await token_service.introspect_token(token=request.token, token_id=request.token_id)
        return APIResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
