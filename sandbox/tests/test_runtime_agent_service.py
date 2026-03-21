import pytest

from app.domain.models.event import (
    DoneEvent,
    MessageEvent,
    PlanEvent,
    PlanStatus,
    StepEvent,
    StepStatus,
    TitleEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.plan import Plan, Step
from app.services.runtime_agent import RuntimeAgentService


class FakeGatewayRuntime:
    def get_chat_model_kwargs(self, session_id: str):
        return {
            "model": "gpt-4o-mini",
            "model_provider": "openai",
            "base_url": "http://gateway:8100/v1",
            "default_headers": {"Authorization": "Bearer token"},
            "temperature": 0.7,
            "max_tokens": 2000,
        }


class FakeFlow:
    def __init__(self, events):
        self._events = events

    async def run(self, message, session_status="pending", last_plan=None):
        _ = (message, session_status, last_plan)
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_runtime_agent_service_maps_flow_events_to_runtime_protocol(monkeypatch):
    service = RuntimeAgentService(FakeGatewayRuntime())
    plan = Plan(
        title="Demo Plan",
        goal="run shell",
        language="zh",
        steps=[Step(id="1", description="run shell command")],
    )
    step = Step(id="1", description="run shell command")

    flow = FakeFlow(
        [
            TitleEvent(title="Demo Plan"),
            PlanEvent(status=PlanStatus.CREATED, plan=plan),
            MessageEvent(message="start"),
            StepEvent(status=StepStatus.STARTED, step=step),
            ToolEvent(
                status=ToolStatus.CALLING,
                tool_call_id="call_1",
                tool_name="shell",
                function_name="shell_exec",
                function_args={"id": "sid_1", "exec_dir": "/tmp", "command": "echo hello"},
            ),
            ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id="call_1",
                tool_name="shell",
                function_name="shell_exec",
                function_args={"id": "sid_1", "exec_dir": "/tmp", "command": "echo hello"},
                function_result={"success": True, "data": {"id": "sid_1", "console": []}},
            ),
            StepEvent(status=StepStatus.COMPLETED, step=step),
            MessageEvent(message="done"),
            DoneEvent(),
        ]
    )

    monkeypatch.setattr(service, "_build_flow", lambda **kwargs: flow)

    out = []
    async for event_name, payload in service.run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox_id="sbx1",
        user_message="run shell then finish",
        attachments=[],
        session_status="pending",
        last_plan=None,
    ):
        out.append((event_name, payload))

    assert [name for name, _ in out] == [
        "title",
        "plan",
        "message",
        "step",
        "tool",
        "tool",
        "step",
        "message",
        "done",
    ]
    assert out[0][1]["type"] == "title"
    assert out[0][1]["title"] == "Demo Plan"
    assert out[1][1]["type"] == "plan"
    assert out[1][1]["status"] == "created"
    assert out[2][1]["type"] == "message"
    assert out[2][1]["role"] == "assistant"
    assert out[4][1]["type"] == "tool"
    assert out[4][1]["tool_name"] == "shell"
    assert out[4][1]["status"] == "calling"
    assert out[5][1]["status"] == "called"
    assert out[5][1]["function_args"]["id"] == "sid_1"
    assert out[-1][1]["type"] == "done"


@pytest.mark.asyncio
async def test_runtime_agent_service_maps_wait_event(monkeypatch):
    service = RuntimeAgentService(FakeGatewayRuntime())
    flow = FakeFlow([MessageEvent(message="请先登录后继续"), WaitEvent()])
    monkeypatch.setattr(service, "_build_flow", lambda **kwargs: flow)

    out = []
    async for event_name, payload in service.run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox_id="sbx1",
        user_message="need login",
        attachments=[],
        session_status="pending",
        last_plan=None,
    ):
        out.append((event_name, payload))

    assert [name for name, _ in out] == ["message", "wait"]
    assert out[-1][1]["type"] == "wait"


@pytest.mark.asyncio
async def test_runtime_agent_service_returns_error_on_unhandled_exception(monkeypatch):
    service = RuntimeAgentService(FakeGatewayRuntime())

    def _raise_build_flow(**kwargs):
        raise RuntimeError("flow init failed")

    monkeypatch.setattr(service, "_build_flow", _raise_build_flow)

    out = []
    async for event_name, payload in service.run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        sandbox_id="sbx1",
        user_message="hello",
        attachments=[],
        session_status="pending",
        last_plan=None,
    ):
        out.append((event_name, payload))

    assert out[0][0] == "error"
    assert out[0][1]["type"] == "error"
    assert out[0][1]["error"] == "flow init failed"
