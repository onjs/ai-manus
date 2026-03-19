import pytest

from app.domain.models.event import ToolEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.gateway_task_runner import GatewayTaskRunner
from app.infrastructure.external.gateway.client import GatewayStreamEvent
from app.interfaces.schemas.event import EventMapper, ToolSSEEvent


class _FakeSessionRepository:
    async def add_event(self, session_id, event):
        return None

    async def update_status(self, session_id, status):
        return None

    async def update_latest_message(self, session_id, message, timestamp):
        return None

    async def increment_unread_message_count(self, session_id):
        return None


class _FakeGatewayClient:
    def __init__(self):
        self.base_url = "http://gateway:8100"

    async def issue_token(self, **kwargs):
        class Issued:
            token = "token-1"
            token_id = "token-id-1"
            expire_at = 9999999999
            scopes = ["llm:stream"]

        return Issued()

    async def revoke_token(self, token_id, reason="revoked"):
        return None


class _FakeSandbox:
    id = "sbx1"

    def __init__(self, events):
        self._events = events

    async def runtime_configure_gateway(self, **kwargs):
        return ToolResult(success=True, data={"configured": True})

    async def runtime_clear_gateway(self, session_id):
        return ToolResult(success=True, data={"cleared": True})

    async def runtime_cancel_runner(self, session_id):
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
async def test_gateway_tool_pipeline_search_event_maps_to_stable_sse_fields():
    sandbox = _FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "search",
                "function_name": "info_search_web",
                "tool_call_id": "call_search",
                "function_args": {"query": "ai-manus"},
                "status": "called",
                "function_result": {
                    "data": {
                        "query": "ai-manus",
                        "results": [{"title": "A", "link": "https://a.com", "snippet": "s"}],
                    }
                },
            },
            {"seq": 2, "event": "done"},
        ]
    )
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=_FakeSessionRepository(),
        gateway_client=_FakeGatewayClient(),
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = next(e for e in out if isinstance(e, ToolEvent))

    sse_event = await EventMapper.event_to_sse_event(tool_event)
    assert isinstance(sse_event, ToolSSEEvent)
    assert sse_event.data.name == "search"
    assert sse_event.data.function == "info_search_web"
    assert sse_event.data.status.value == "called"
    assert sse_event.data.args["query"] == "ai-manus"
    assert sse_event.data.content is not None
    assert sse_event.data.content.results[0].link == "https://a.com"


@pytest.mark.asyncio
async def test_gateway_tool_pipeline_mcp_event_maps_to_stable_sse_fields():
    sandbox = _FakeSandbox(
        [
            {
                "seq": 1,
                "event": "tool",
                "tool_name": "mcp",
                "function_name": "mcp_demo_ping",
                "tool_call_id": "call_mcp",
                "function_args": {"x": 1},
                "status": "called",
                "function_result": {
                    "data": {"ok": True, "payload": {"x": 1}},
                },
            },
            {"seq": 2, "event": "done"},
        ]
    )
    runner = GatewayTaskRunner(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox=sandbox,
        session_repository=_FakeSessionRepository(),
        gateway_client=_FakeGatewayClient(),
    )

    out = [event async for event in runner._run_gateway_flow("test")]  # noqa: SLF001
    tool_event = next(e for e in out if isinstance(e, ToolEvent))

    sse_event = await EventMapper.event_to_sse_event(tool_event)
    assert isinstance(sse_event, ToolSSEEvent)
    assert sse_event.data.name == "mcp"
    assert sse_event.data.function == "mcp_demo_ping"
    assert sse_event.data.status.value == "called"
    assert sse_event.data.args == {"x": 1}
    assert sse_event.data.content is not None
    assert sse_event.data.content.result == {"ok": True, "payload": {"x": 1}}
