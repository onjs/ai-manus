import asyncio

import pytest

from app.schemas.runtime_runner import RuntimeRunnerStartRequest
from app.services.runtime_runner import RuntimeRunnerService
from app.services.runtime_run_registry import RuntimeRunRegistry


class FakeRuntimeService:
    def __init__(self, has_config: bool = True):
        self._has_config = has_config

    def has_gateway_config(self, session_id: str) -> bool:
        _ = session_id
        return self._has_config


@pytest.mark.asyncio
async def test_runner_service_start_cancel_clear():
    runtime = FakeRuntimeService(has_config=True)
    service = RuntimeRunnerService(runtime)
    service._registry = RuntimeRunRegistry()  # noqa: SLF001

    complete_signal = pytest.MonkeyPatch()
    marker = {"done": False}

    async def fake_run(**kwargs):
        _ = kwargs
        while not marker["done"]:
            await asyncio.sleep(0.01)
        yield "done", {}

    complete_signal.setattr(service._runtime_agent, "run", fake_run, raising=True)  # noqa: SLF001

    request = RuntimeRunnerStartRequest(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox_id="sbx1",
        message="hello",
        session_status="running",
    )
    started = await service.start_run(request)
    second = await service.start_run(request)
    assert started["started"] is True
    assert second["started"] is False

    cancelled = await service.cancel_run("s1")
    assert cancelled["cancelled"] is True

    cleared = await service.clear_run("s1")
    assert cleared["cleared"] is True

    complete_signal.undo()


@pytest.mark.asyncio
async def test_runner_service_requires_gateway_config():
    runtime = FakeRuntimeService(has_config=False)
    service = RuntimeRunnerService(runtime)
    service._registry = RuntimeRunRegistry()  # noqa: SLF001

    with pytest.raises(ValueError, match="not configured"):
        await service.start_run(
            RuntimeRunnerStartRequest(
                session_id="s1",
                agent_id="a1",
                user_id="u1",
                sandbox_id="sbx1",
                message="hello",
                session_status="running",
            )
        )


@pytest.mark.asyncio
async def test_runner_service_stream_events_resume_from_seq_without_duplicates():
    runtime = FakeRuntimeService(has_config=True)
    service = RuntimeRunnerService(runtime)
    service._registry = RuntimeRunRegistry()  # noqa: SLF001
    registry = service._registry  # noqa: SLF001

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

    first_connection = []
    async for event_name, data in service.stream_events("s1", from_seq=1, limit=1):
        first_connection.append((event_name, data))

    reconnect = []
    async for event_name, data in service.stream_events("s1", from_seq=2, limit=10):
        reconnect.append((event_name, data))

    assert [item[1]["seq"] for item in first_connection if item[0] == "message"] == [1]
    assert [item[1]["seq"] for item in reconnect if item[0] in {"tool", "done"}] == [2, 3]


@pytest.mark.asyncio
async def test_runner_service_stream_events_stops_on_waiting_status():
    runtime = FakeRuntimeService(has_config=True)
    service = RuntimeRunnerService(runtime)
    service._registry = RuntimeRunRegistry()  # noqa: SLF001
    registry = service._registry  # noqa: SLF001

    await registry.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="waiting",
        message="hello",
        error=None,
        reset_events=True,
    )
    await registry.append_event("s1", "message", {"role": "assistant", "message": "请先登录后继续"})
    await registry.append_event("s1", "wait", {"reason": "login_required"})

    out = []
    async for event_name, data in service.stream_events("s1", from_seq=1, limit=10):
        out.append((event_name, data))

    assert [event for event, _ in out] == ["message", "wait"]
    assert [payload["seq"] for _, payload in out] == [1, 2]


@pytest.mark.asyncio
async def test_runner_service_cancel_noop_for_terminal_status():
    runtime = FakeRuntimeService(has_config=True)
    service = RuntimeRunnerService(runtime)
    service._registry = RuntimeRunRegistry()  # noqa: SLF001
    registry = service._registry  # noqa: SLF001

    await registry.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="completed",
        message="done",
        error=None,
        reset_events=True,
    )

    result = await service.cancel_run("s1")
    assert result["cancelled"] is False
    assert result["reason"] == "not_running"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_runner_service_executes_agent_stream_and_marks_completed():
    runtime = FakeRuntimeService(has_config=True)
    service = RuntimeRunnerService(runtime)
    service._registry = RuntimeRunRegistry()  # noqa: SLF001

    async def fake_run(**kwargs):
        _ = kwargs
        yield "message", {"role": "assistant", "message": "ok"}
        yield "done", {}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service._runtime_agent, "run", fake_run, raising=True)  # noqa: SLF001

    await service.start_run(
        RuntimeRunnerStartRequest(
            session_id="s1",
            agent_id="a1",
            user_id="u1",
            sandbox_id="sbx1",
            message="hello",
            session_status="running",
        )
    )

    for _ in range(50):
        status = await service.get_status("s1")
        if status.get("status") == "completed":
            break
        await asyncio.sleep(0.01)

    events = await service.get_events("s1", from_seq=1, limit=10)
    assert [item["event"] for item in events["events"]] == ["message", "done"]
    assert events["status"] == "completed"
    monkeypatch.undo()
