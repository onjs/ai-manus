import asyncio

import pytest

from app.runner.daemon import RuntimeRunnerDaemon
from app.services.runtime_store import RuntimeStore


class FakeGatewayRuntime:
    pass


class FakeSearchRuntimeAgent:
    async def run(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        yield (
            "tool",
            {
                "tool_name": "search",
                "function_name": "info_search_web",
                "function_args": {"query": "ai-manus"},
                "tool_call_id": "call-1",
                "status": "calling",
                "function_result": None,
            },
        )
        yield (
            "tool",
            {
                "tool_name": "search",
                "function_name": "info_search_web",
                "function_args": {"query": "ai-manus"},
                "tool_call_id": "call-1",
                "status": "called",
                "function_result": {
                    "success": True,
                    "message": "ok",
                    "data": {
                        "query": "ai-manus",
                        "results": [
                            {
                                "title": "ai-manus",
                                "link": "https://example.com/ai-manus",
                                "snippet": "result",
                            }
                        ],
                    },
                },
            },
        )
        yield ("done", {"session_id": "s_search_chain"})


class FakeMCPRuntimeAgent:
    async def run(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        yield (
            "tool",
            {
                "tool_name": "mcp",
                "function_name": "mcp_demo_ping",
                "function_args": {"q": "hello"},
                "tool_call_id": "call-1",
                "status": "calling",
                "function_result": None,
            },
        )
        yield (
            "tool",
            {
                "tool_name": "mcp",
                "function_name": "mcp_demo_ping",
                "function_args": {"q": "hello"},
                "tool_call_id": "call-1",
                "status": "called",
                "function_result": {
                    "success": True,
                    "message": "ok",
                    "data": {
                        "server": "demo",
                        "tool": "mcp_demo_ping",
                        "result": {"echo": {"q": "hello"}},
                    },
                },
            },
        )
        yield ("done", {"session_id": "s_mcp_chain"})


async def _wait_run_completed(store: RuntimeStore, session_id: str, timeout_sec: float = 2.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while asyncio.get_running_loop().time() < deadline:
        run = store.get_run(session_id)
        if run and run["status"] in {"completed", "failed", "cancelled", "waiting"}:
            return run
        await asyncio.sleep(0.05)
    raise AssertionError(f"run did not finish within {timeout_sec}s")


def _seed_start_command(store: RuntimeStore, session_id: str, message: str) -> None:
    store.set_gateway_credential(
        session_id=session_id,
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )
    store.upsert_run(
        session_id=session_id,
        agent_id="a1",
        user_id="u1",
        status="starting",
        message=message,
        reset_events=True,
    )
    store.enqueue_command(
        session_id=session_id,
        command_type="start",
        payload={
            "session_id": session_id,
            "agent_id": "a1",
            "user_id": "u1",
            "sandbox_id": "sbx1",
            "message": message,
        },
    )


@pytest.mark.asyncio
async def test_runtime_runner_daemon_executes_search_tool_chain(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime_search_chain.db"))
    session_id = "s_search_chain"
    _seed_start_command(store, session_id, "search now")

    daemon = RuntimeRunnerDaemon(store, FakeGatewayRuntime(), FakeSearchRuntimeAgent())
    await daemon._process_pending_commands()  # noqa: SLF001

    run = await _wait_run_completed(store, session_id)
    assert run["status"] == "completed"

    events = store.get_events(session_id, from_seq=1, limit=50)
    event_names = [event["event"] for event in events]
    assert "tool" in event_names
    assert event_names[-1] == "done"

    search_result = next(
        event
        for event in events
        if event["event"] == "tool"
        and event["data"].get("tool_name") == "search"
        and event["data"].get("status") == "called"
    )
    assert search_result["data"]["function_args"]["query"] == "ai-manus"
    assert search_result["data"]["function_result"]["data"]["results"][0]["link"] == "https://example.com/ai-manus"


@pytest.mark.asyncio
async def test_runtime_runner_daemon_executes_mcp_tool_chain(tmp_path):
    store = RuntimeStore(db_path=str(tmp_path / "runtime_mcp_chain.db"))
    session_id = "s_mcp_chain"
    _seed_start_command(store, session_id, "mcp now")

    daemon = RuntimeRunnerDaemon(store, FakeGatewayRuntime(), FakeMCPRuntimeAgent())
    await daemon._process_pending_commands()  # noqa: SLF001

    run = await _wait_run_completed(store, session_id)
    assert run["status"] == "completed"

    events = store.get_events(session_id, from_seq=1, limit=50)
    event_names = [event["event"] for event in events]
    assert "tool" in event_names
    assert event_names[-1] == "done"

    mcp_result = next(
        event
        for event in events
        if event["event"] == "tool"
        and event["data"].get("tool_name") == "mcp"
        and event["data"].get("status") == "called"
    )
    assert mcp_result["data"]["function_name"] == "mcp_demo_ping"
    assert mcp_result["data"]["function_result"]["data"]["result"]["echo"] == {"q": "hello"}
