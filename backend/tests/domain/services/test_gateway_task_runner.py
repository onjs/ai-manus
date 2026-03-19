import pytest

from app.domain.models.event import DoneEvent, ErrorEvent, MessageEvent, PlanEvent, StepEvent, TitleEvent, ToolEvent, WaitEvent
from app.domain.services.gateway_task_runner import GatewayTaskRunner
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.gateway.client import GatewayStreamEvent


class FakeSessionRepository:
    async def add_event(self, session_id, event):
        return None

    async def update_status(self, session_id, status):
        return None

    async def update_latest_message(self, session_id, message, timestamp):
        return None

    async def increment_unread_message_count(self, session_id):
        return None


class FakeGatewayClient:
    def __init__(self):
        self.base_url = "http://gateway:8100"
        self.revoked = []

    async def issue_token(self, **kwargs):
        class Issued:
            token = "token-1"
            token_id = "token-id-1"
            expire_at = 9999999999
            scopes = ["llm:stream"]
        return Issued()

    async def revoke_token(self, token_id, reason="revoked"):
        self.revoked.append((token_id, reason))


class FakeSandbox:
    id = "sbx1"

    def __init__(self, events):
        self._events = events
        self.configured = []
        self.cleared = []
        self.cancelled = []

    async def runtime_configure_gateway(self, **kwargs):
        self.configured.append(kwargs)
        return ToolResult(success=True, data={"configured": True})

    async def runtime_clear_gateway(self, session_id):
        self.cleared.append(session_id)
        return ToolResult(success=True, data={"cleared": True})

    async def runtime_cancel_runner(self, session_id):
        self.cancelled.append(session_id)
        return ToolResult(success=True)

    async def runtime_start_runner(self, **kwargs):
        return ToolResult(success=True, data={"started": True})

    async def runtime_stream_runner_events(self, **kwargs):
        from_seq = kwargs.get("from_seq", 1)
        for event in self._events:
            if int(event.get("seq", 0)) < from_seq:
                continue
            event_name = str(event["event"])
            payload = {k: v for k, v in event.items() if k != "event"}
            yield GatewayStreamEvent(event=event_name, data=payload)

@pytest.mark.asyncio
async def test_gateway_flow_maps_chunk_to_message_and_done():
    sandbox = FakeSandbox(
        [
            {"seq": 1, "event": "message", "role": "assistant", "message": "hello world"},
            {"seq": 3, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    assert isinstance(out[0], MessageEvent)
    assert out[0].message == "hello world"
    assert isinstance(out[-1], DoneEvent)


@pytest.mark.asyncio
async def test_gateway_flow_maps_tool_events():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "browser",
                "function_name": "browser_click",
                "tool_call_id": "call_1",
                "function_args": {"selector": "#id"},
                "status": "calling",
                "function_result": None,
            },
            {
                "seq": 2,
                "event": "tool",
                "tool_name": "browser",
                "function_name": "browser_click",
                "tool_call_id": "call_1",
                "function_args": {"selector": "#id"},
                "status": "called",
                "function_result": {"ok": True},
            },
            {"seq": 3, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    assert isinstance(out[0], ToolEvent)
    assert out[0].status.value == "calling"
    assert isinstance(out[1], ToolEvent)
    assert out[1].status.value == "called"
    assert out[1].function_result == {"ok": True}


@pytest.mark.asyncio
async def test_gateway_flow_maps_title_plan_step_lifecycle_events():
    sandbox = FakeSandbox(
        [
            {"seq": 1, "event": "title", "title": "采购自动化任务"},
            {
                "seq": 2,
                "event": "plan",
                "status": "created",
                "plan": {
                    "goal": "完成采购单提报",
                    "language": "zh",
                    "steps": [
                        {"id": "1", "description": "登录系统并进入工作项页面", "status": "pending"},
                    ],
                },
            },
            {
                "seq": 3,
                "event": "step",
                "status": "started",
                "step": {
                    "id": "1",
                    "description": "登录系统并进入工作项页面",
                    "status": "running",
                },
            },
            {"seq": 4, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    assert isinstance(out[0], TitleEvent)
    assert out[0].title == "采购自动化任务"

    assert isinstance(out[1], PlanEvent)
    assert out[1].status.value == "created"
    assert out[1].plan.steps[0].description == "登录系统并进入工作项页面"

    assert isinstance(out[2], StepEvent)
    assert out[2].status.value == "started"
    assert out[2].step.status.value == "running"

    assert isinstance(out[3], DoneEvent)


@pytest.mark.asyncio
async def test_gateway_flow_maps_wait_event():
    sandbox = FakeSandbox(
        [
            {"seq": 1, "event": "message", "message": "请先登录"},
            {"seq": 2, "event": "wait"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    assert isinstance(out[0], MessageEvent)
    assert out[0].message == "请先登录"
    assert isinstance(out[1], WaitEvent)


@pytest.mark.asyncio
async def test_gateway_flow_maps_shell_and_file_tool_content():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "shell",
                "function_name": "shell_exec",
                "tool_call_id": "call_shell",
                "function_args": {"id": "sh_1"},
                "status": "called",
                "function_result": {
                    "data": {
                        "console": [{"ps1": "$", "command": "ls", "output": "a.txt"}],
                    }
                },
            },
            {
                "seq": 2,
                "event": "tool",
                "tool_name": "file",
                "function_name": "file_read",
                "tool_call_id": "call_file",
                "function_args": {"file": "/home/ubuntu/a.txt"},
                "status": "called",
                "function_result": {
                    "data": {"content": "hello world"},
                },
            },
            {"seq": 3, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    shell_event = out[0]
    file_event = out[1]

    assert isinstance(shell_event, ToolEvent)
    assert shell_event.tool_content is not None
    assert shell_event.function_args["id"] == "sh_1"
    assert shell_event.tool_content.console[0]["command"] == "ls"

    assert isinstance(file_event, ToolEvent)
    assert file_event.tool_content is not None
    assert file_event.function_args["file"] == "/home/ubuntu/a.txt"
    assert file_event.tool_content.content == "hello world"


@pytest.mark.asyncio
async def test_gateway_flow_shell_result_normalizes_session_id_from_args():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "shell",
                "function_name": "shell_exec",
                "tool_call_id": "call_shell",
                "function_args": {"session_id": "shell_123"},
                "status": "called",
                "function_result": {"data": {"console": []}},
            },
            {"seq": 2, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = out[0]
    assert isinstance(tool_event, ToolEvent)
    assert tool_event.function_args["id"] == "shell_123"


@pytest.mark.asyncio
async def test_gateway_flow_shell_result_normalizes_session_id_from_result_data():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "shell",
                "function_name": "shell_exec",
                "tool_call_id": "call_shell",
                "function_args": {},
                "status": "called",
                "function_result": {"data": {"id": "shell_456", "console": []}},
            },
            {"seq": 2, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = out[0]
    assert isinstance(tool_event, ToolEvent)
    assert tool_event.function_args["id"] == "shell_456"


@pytest.mark.asyncio
async def test_gateway_flow_file_result_normalizes_path_from_result_data():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "file",
                "function_name": "file_read",
                "tool_call_id": "call_file",
                "function_args": {},
                "status": "called",
                "function_result": {"data": {"file_path": "/tmp/from-result.txt", "content": "x"}},
            },
            {"seq": 2, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = out[0]
    assert isinstance(tool_event, ToolEvent)
    assert tool_event.function_args["file"] == "/tmp/from-result.txt"


@pytest.mark.asyncio
async def test_gateway_flow_search_result_normalizes_query_from_args_and_result_data():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "search",
                "function_name": "info_search_web",
                "tool_call_id": "call_search_1",
                "function_args": {"q": "deepseek"},
                "status": "called",
                "function_result": {
                    "data": {"results": [{"title": "A", "url": "https://a.com", "description": "desc"}]}
                },
            },
            {
                "seq": 2,
                "event": "tool",
                "tool_name": "search",
                "function_name": "info_search_web",
                "tool_call_id": "call_search_2",
                "function_args": {},
                "status": "called",
                "function_result": {
                    "data": {
                        "query": "autonomous procurement",
                        "results": [{"title": "B", "link": "https://b.com", "snippet": "s"}],
                    }
                },
            },
            {"seq": 3, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    search_from_q = out[0]
    search_from_result = out[1]
    assert isinstance(search_from_q, ToolEvent)
    assert search_from_q.function_args["query"] == "deepseek"
    assert search_from_q.tool_content is not None
    assert search_from_q.tool_content.results[0].link == "https://a.com"
    assert isinstance(search_from_result, ToolEvent)
    assert search_from_result.function_args["query"] == "autonomous procurement"


@pytest.mark.asyncio
async def test_gateway_flow_maps_mcp_tool_content():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "mcp",
                "function_name": "mcp_query",
                "tool_call_id": "call_mcp",
                "function_args": {"query": "a"},
                "status": "called",
                "function_result": {
                    "data": {"items": [1, 2, 3]},
                },
            },
            {"seq": 2, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = out[0]
    assert isinstance(tool_event, ToolEvent)
    assert tool_event.tool_content is not None
    assert tool_event.tool_content.result == {"items": [1, 2, 3]}


@pytest.mark.asyncio
async def test_gateway_flow_maps_browser_preview_screenshot():
    sandbox = FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "browser",
                "function_name": "browser_click",
                "tool_call_id": "call_browser",
                "function_args": {"selector": "#new"},
                "status": "called",
                "function_result": {
                    "data": {
                        "screenshot_url": "https://example.com/snap.png",
                        "status": "ok",
                    }
                },
            },
            {"seq": 2, "event": "done"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = out[0]
    assert isinstance(tool_event, ToolEvent)
    assert tool_event.tool_content is not None
    assert tool_event.tool_content.screenshot == "https://example.com/snap.png"


@pytest.mark.asyncio
async def test_gateway_flow_error_event_stops_with_error():
    sandbox = FakeSandbox(
        [
            {"seq": 1, "event": "error", "error": "user_input_required"},
        ]
    )
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    assert len(out) == 1
    assert isinstance(out[0], ErrorEvent)


@pytest.mark.asyncio
async def test_gateway_flow_stream_interrupt_yields_error_event():
    class BrokenStreamSandbox(FakeSandbox):
        async def runtime_stream_runner_events(self, **kwargs):
            raise RuntimeError("sse connection lost")
            yield  # pragma: no cover

    sandbox = BrokenStreamSandbox([])
    client = FakeGatewayClient()
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=client,
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    assert len(out) == 1
    assert isinstance(out[0], ErrorEvent)
    assert "Sandbox runner stream interrupted" in out[0].error
