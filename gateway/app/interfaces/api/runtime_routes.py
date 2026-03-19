from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.auth import require_scope
from app.core.config import Settings, get_settings
from app.infrastructure.providers.base_provider import BaseLLMProvider
from app.infrastructure.providers.factory import ProviderFactory

router = APIRouter(tags=["openai"])


def _get_provider(settings: Settings = Depends(get_settings)) -> BaseLLMProvider:
    return ProviderFactory.create(settings)


def _validate_chat_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request body must be a JSON object",
        )
    messages = payload.get("messages")
    if not isinstance(messages, list) or len(messages) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="messages is required and must be a non-empty array",
        )
    return payload


@router.post("/v1/chat/completions", dependencies=[Depends(require_scope("llm:stream"))])
async def chat_completions(
    request: Request,
    provider: BaseLLMProvider = Depends(_get_provider),
):
    payload = _validate_chat_payload(await request.json())
    stream = bool(payload.get("stream"))

    if stream:
        return StreamingResponse(
            provider.stream_chat_completion(payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    data = await provider.create_chat_completion(payload)
    return JSONResponse(content=data)
