import asyncio
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.runtime_runner import router as runtime_runner_router
from app.core.config import settings
from app.schemas.runtime_runner import RuntimeRunnerStartRequest
from app.services.runtime import runtime_service
from app.services.runtime_credential_store import RuntimeCredentialStore
from app.services.runtime_run_registry import RuntimeRunRegistry
from app.services.runtime_runner import runtime_runner_service


def _decode_sse_payload(data_lines: list[str]) -> dict:
    data_str = "\n".join(data_lines).strip()
    if not data_str:
        return {}
    return json.loads(data_str)


async def _read_sse_events(response, max_events: int | None = None) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line:
            if event_name or data_lines:
                events.append((event_name or "message", _decode_sse_payload(data_lines)))
                if max_events is not None and len(events) >= max_events:
                    break
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    return events


@pytest.fixture
def isolated_runtime_state(tmp_path, monkeypatch):
    store = RuntimeCredentialStore(base_dir=str(tmp_path / "runtime_api"))
    registry = RuntimeRunRegistry()
    monkeypatch.setattr(runtime_service, "_store", store, raising=False)
    monkeypatch.setattr(runtime_runner_service, "_registry", registry, raising=False)
    monkeypatch.setattr(runtime_runner_service, "_gateway_runtime", runtime_service, raising=False)
    return store, registry


@pytest.fixture
def runtime_runner_api_app():
    test_app = FastAPI()
    test_app.include_router(runtime_runner_router, prefix="/api/v1/runtime")
    return test_app


@pytest.mark.asyncio
async def test_runtime_runner_start_is_idempotent_via_api(isolated_runtime_state, runtime_runner_api_app):
    store, _registry = isolated_runtime_state
    keep_running = {"on": True}

    async def fake_run(**kwargs):
        _ = kwargs
        while keep_running["on"]:
            await asyncio.sleep(0.01)
        yield "done", {}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runtime_runner_service._runtime_agent, "run", fake_run, raising=True)  # noqa: SLF001

    store.set_gateway_credential(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )

    request = RuntimeRunnerStartRequest(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox_id="sbx1",
        message="hello",
        session_status="running",
    )
    headers = {"X-Internal-Key": settings.SANDBOX_INTERNAL_API_KEY, "Content-Type": "application/json"}
    transport = ASGITransport(app=runtime_runner_api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post("/api/v1/runtime/runs/start", headers=headers, json=request.model_dump())
        second = await client.post("/api/v1/runtime/runs/start", headers=headers, json=request.model_dump())
        await client.post("/api/v1/runtime/runs/s1/cancel", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["started"] is True
    assert second.json()["data"]["started"] is False
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_runtime_runner_stream_reconnect_from_seq_via_api(isolated_runtime_state, runtime_runner_api_app):
    _store, registry = isolated_runtime_state
    await registry.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="completed",
        message="hello",
        error=None,
        reset_events=True,
    )
    await registry.append_event("s1", "message", {"role": "assistant", "message": "hello"})
    await registry.append_event(
        "s1",
        "tool",
        {
            "tool_name": "browser",
            "function_name": "browser_click",
            "function_args": {"selector": "#submit"},
            "tool_call_id": "call_1",
            "status": "calling",
            "function_result": None,
        },
    )
    await registry.append_event("s1", "done", {})

    headers = {"X-Internal-Key": settings.SANDBOX_INTERNAL_API_KEY}
    transport = ASGITransport(app=runtime_runner_api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "GET",
            "/api/v1/runtime/runs/s1/events/stream",
            headers=headers,
            params={"from_seq": 1, "limit": 1},
        ) as response:
            assert response.status_code == 200
            first_events = await _read_sse_events(response, max_events=1)

        async with client.stream(
            "GET",
            "/api/v1/runtime/runs/s1/events/stream",
            headers=headers,
            params={"from_seq": 2, "limit": 10},
        ) as response:
            assert response.status_code == 200
            resumed_events = await _read_sse_events(response)

    first_seq = [payload["seq"] for event, payload in first_events if event == "message"]
    resumed_seq = [payload["seq"] for event, payload in resumed_events if event in {"tool", "done"}]

    assert first_seq == [1]
    assert resumed_seq == [2, 3]

    # Queue semantics: all delivered events are removed from in-memory queue.
    remaining = await registry.get_events("s1", from_seq=1, limit=10)
    assert remaining == []


@pytest.mark.asyncio
async def test_runtime_runner_rejects_invalid_session_id(runtime_runner_api_app):
    headers = {"X-Internal-Key": settings.SANDBOX_INTERNAL_API_KEY, "Content-Type": "application/json"}
    payload = {
        "session_id": "../bad",
        "agent_id": "a1",
        "user_id": "u1",
        "sandbox_id": "sbx1",
        "message": "hello",
        "attachments": [],
        "session_status": "running",
        "last_plan": None,
    }

    transport = ASGITransport(app=runtime_runner_api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/runtime/runs/start", headers=headers, json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid session_id format"
