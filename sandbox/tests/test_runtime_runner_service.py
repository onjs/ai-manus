import pytest

from app.schemas.runtime_runner import RuntimeRunnerStartRequest
from app.services.runtime_runner import RuntimeRunnerService
from app.services.runtime_store import RuntimeStore


class FakeRuntimeService:
    def __init__(self, store: RuntimeStore):
        self._store = store

    def has_gateway_config(self, session_id: str) -> bool:
        return self._store.has_gateway_credential(session_id)


@pytest.mark.asyncio
async def test_runner_service_enqueues_start_cancel_clear(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime.db"))
    runtime = FakeRuntimeService(store)
    service = RuntimeRunnerService(runtime)
    service._store = store  # use isolated db for this test

    store.set_gateway_credential(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )

    started = await service.start_run(
        RuntimeRunnerStartRequest(
            session_id="s1",
            agent_id="a1",
            user_id="u1",
            sandbox_id="sbx1",
            message="hello",
        )
    )
    assert started["started"] is True
    run = store.get_run("s1")
    assert run is not None
    assert run["status"] == "starting"

    pending = store.get_pending_commands(limit=10)
    assert len(pending) == 1
    assert pending[0]["command_type"] == "start"
    store.mark_command_done(pending[0]["id"])

    cancel = await service.cancel_run("s1")
    assert cancel["cancelled"] is True
    pending = store.get_pending_commands(limit=10)
    assert len(pending) == 1
    assert pending[0]["command_type"] == "cancel"
    store.mark_command_done(pending[0]["id"])

    cleared = await service.clear_run("s1")
    assert cleared["cleared"] is True
    pending = store.get_pending_commands(limit=10)
    assert len(pending) == 1
    assert pending[0]["command_type"] == "clear"


@pytest.mark.asyncio
async def test_runner_service_requires_gateway_config(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime.db"))
    runtime = FakeRuntimeService(store)
    service = RuntimeRunnerService(runtime)
    service._store = store

    with pytest.raises(ValueError, match="not configured"):
        await service.start_run(
            RuntimeRunnerStartRequest(
                session_id="s1",
                agent_id="a1",
                user_id="u1",
                sandbox_id="sbx1",
                message="hello",
            )
        )


@pytest.mark.asyncio
async def test_runner_service_start_is_idempotent_when_already_running(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime.db"))
    runtime = FakeRuntimeService(store)
    service = RuntimeRunnerService(runtime)
    service._store = store

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
    )
    first = await service.start_run(request)
    second = await service.start_run(request)

    assert first["started"] is True
    assert second["started"] is False
    pending = store.get_pending_commands(limit=10)
    assert len(pending) == 1
    assert pending[0]["command_type"] == "start"


@pytest.mark.asyncio
async def test_runner_service_stream_events_resume_from_seq_without_duplicates(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime.db"))
    runtime = FakeRuntimeService(store)
    service = RuntimeRunnerService(runtime)
    service._store = store

    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="completed",
        message="hello",
        reset_events=True,
    )
    store.append_event("s1", "message", {"role": "assistant", "message": "hello"})
    store.append_event(
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
    store.append_event("s1", "done", {})

    first_connection = []
    async for event_name, data in service.stream_events("s1", from_seq=1, limit=1):
        first_connection.append((event_name, data))

    reconnect = []
    async for event_name, data in service.stream_events("s1", from_seq=2, limit=10):
        reconnect.append((event_name, data))

    assert [item[1]["seq"] for item in first_connection if item[0] == "message"] == [1]
    assert [item[1]["seq"] for item in reconnect if item[0] in {"tool", "done"}] == [2, 3]


@pytest.mark.asyncio
async def test_runner_service_stream_events_stops_on_waiting_status(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime_waiting.db"))
    runtime = FakeRuntimeService(store)
    service = RuntimeRunnerService(runtime)
    service._store = store

    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="waiting",
        message="hello",
        reset_events=True,
    )
    store.append_event("s1", "message", {"role": "assistant", "message": "请先登录后继续"})
    store.append_event("s1", "wait", {"reason": "login_required"})

    out = []
    async for event_name, data in service.stream_events("s1", from_seq=1, limit=10):
        out.append((event_name, data))

    assert [event for event, _ in out] == ["message", "wait"]
    assert [payload["seq"] for _, payload in out] == [1, 2]


@pytest.mark.asyncio
async def test_runner_service_cancel_noop_for_terminal_status(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime_terminal.db"))
    runtime = FakeRuntimeService(store)
    service = RuntimeRunnerService(runtime)
    service._store = store

    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="completed",
        message="done",
        reset_events=True,
    )

    result = await service.cancel_run("s1")
    assert result["cancelled"] is False
    assert result["reason"] == "not_running"
    assert result["status"] == "completed"
    assert store.get_pending_commands(limit=10) == []
