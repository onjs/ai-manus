import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.schemas.response import Response
from app.schemas.runtime_runner import RuntimeRunnerStartRequest
from app.services.runtime_runner import runtime_runner_service

router = APIRouter()


def verify_runtime_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    if x_internal_key != settings.SANDBOX_INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.post("/runs/start", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def start_runner(request: RuntimeRunnerStartRequest):
    try:
        result = await runtime_runner_service.start_run(request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return Response(success=True, message="Runtime runner started", data=result)


@router.post("/runs/{session_id}/cancel", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def cancel_runner(session_id: str):
    result = await runtime_runner_service.cancel_run(session_id)
    return Response(success=True, message="Runtime runner cancellation requested", data=result)


@router.delete("/runs/{session_id}", response_model=Response, dependencies=[Depends(verify_runtime_internal_key)])
async def clear_runner(session_id: str):
    result = await runtime_runner_service.clear_run(session_id)
    return Response(success=True, message="Runtime runner state cleared", data=result)


@router.get("/runs/{session_id}/events/stream", dependencies=[Depends(verify_runtime_internal_key)])
async def stream_runner_events(
    session_id: str,
    from_seq: int = Query(default=1, ge=1),
    limit: int = Query(default=200, ge=1, le=1000),
):
    async def _event_generator() -> AsyncGenerator[str, None]:
        async for event_name, data in runtime_runner_service.stream_events(
            session_id=session_id,
            from_seq=from_seq,
            limit=limit,
        ):
            yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
