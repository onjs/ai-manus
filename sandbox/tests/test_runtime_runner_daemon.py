import asyncio

import pytest

from app.runner.daemon import RuntimeRunnerDaemon
from app.services.runtime_store import RuntimeStore


class FakeGatewayRuntime:
    pass


class FakeRuntimeAgent:
    async def run(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        yield ("title", {"title": "Demo"})
        yield ("plan", {"status": "running", "plan": {"goal": "g", "steps": []}})
        yield ("message", {"message": "hello"})
        yield ("done", {"session_id": "s1"})


class FakeWaitRuntimeAgent:
    async def run(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        yield ("message", {"message": "请先登录后继续"})
        yield ("wait", {"reason": "login_required"})


@pytest.mark.asyncio
async def test_runtime_runner_daemon_processes_start_command(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime.db"))
    store.set_gateway_credential(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )
    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="starting",
        message="hello",
        reset_events=True,
    )
    store.enqueue_command(
        session_id="s1",
        command_type="start",
        payload={
            "session_id": "s1",
            "agent_id": "a1",
            "user_id": "u1",
            "sandbox_id": "sbx1",
            "message": "hello",
        },
    )

    daemon = RuntimeRunnerDaemon(
        store,
        FakeGatewayRuntime(),
        FakeRuntimeAgent(),
    )
    await daemon._process_pending_commands()  # noqa: SLF001

    for _ in range(20):
        run = store.get_run("s1")
        if run and run["status"] == "completed":
            break
        await asyncio.sleep(0.05)

    run = store.get_run("s1")
    assert run is not None
    assert run["status"] == "completed"

    events = store.get_events("s1", from_seq=1, limit=10)
    assert [e["event"] for e in events] == ["title", "plan", "message", "done"]


@pytest.mark.asyncio
async def test_runtime_runner_daemon_wait_event_marks_waiting(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime_wait.db"))
    store.set_gateway_credential(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )
    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="starting",
        message="hello",
        reset_events=True,
    )
    store.enqueue_command(
        session_id="s1",
        command_type="start",
        payload={
            "session_id": "s1",
            "agent_id": "a1",
            "user_id": "u1",
            "sandbox_id": "sbx1",
            "message": "hello",
        },
    )

    daemon = RuntimeRunnerDaemon(
        store,
        FakeGatewayRuntime(),
        FakeWaitRuntimeAgent(),
    )
    await daemon._process_pending_commands()  # noqa: SLF001

    for _ in range(20):
        run = store.get_run("s1")
        if run and run["status"] == "waiting":
            break
        await asyncio.sleep(0.05)

    run = store.get_run("s1")
    assert run is not None
    assert run["status"] == "waiting"

    events = store.get_events("s1", from_seq=1, limit=10)
    assert [e["event"] for e in events] == ["message", "wait"]


@pytest.mark.asyncio
async def test_runtime_runner_daemon_cancel_does_not_override_terminal_status(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime_cancel_terminal.db"))
    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="completed",
        message="done",
        reset_events=True,
    )
    store.enqueue_command(
        session_id="s1",
        command_type="cancel",
        payload={"session_id": "s1"},
    )

    daemon = RuntimeRunnerDaemon(
        store,
        FakeGatewayRuntime(),
        FakeRuntimeAgent(),
    )
    await daemon._process_pending_commands()  # noqa: SLF001

    run = store.get_run("s1")
    assert run is not None
    assert run["status"] == "completed"
