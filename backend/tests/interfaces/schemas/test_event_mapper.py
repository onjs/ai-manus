import pytest
import json

from app.domain.models.event import ErrorEvent, FileToolContent, ToolEvent, ToolStatus
from app.domain.models.event import BrowserToolContent
from app.interfaces.schemas.event import EventMapper, ErrorSSEEvent, ToolSSEEvent


@pytest.mark.asyncio
async def test_event_mapper_maps_error_event_to_error_sse():
    event = ErrorEvent(error="runner disconnected")
    sse_event = await EventMapper.event_to_sse_event(event)

    assert isinstance(sse_event, ErrorSSEEvent)
    assert sse_event.event == "error"
    assert sse_event.data.error == "runner disconnected"


@pytest.mark.asyncio
async def test_event_mapper_maps_tool_event_with_stable_fields():
    event = ToolEvent(
        tool_call_id="call_1",
        tool_name="file",
        function_name="file_read",
        function_args={"file": "/home/ubuntu/a.txt"},
        status=ToolStatus.CALLED,
        function_result={"ok": True},
        tool_content=FileToolContent(content="hello"),
    )

    sse_event = await EventMapper.event_to_sse_event(event)
    assert isinstance(sse_event, ToolSSEEvent)
    assert sse_event.event == "tool"
    assert sse_event.data.name == "file"
    assert sse_event.data.function == "file_read"
    assert sse_event.data.args == {"file": "/home/ubuntu/a.txt"}
    assert sse_event.data.status == ToolStatus.CALLED
    assert sse_event.data.content is not None
    assert sse_event.data.content.content == "hello"
    payload = json.loads(sse_event.data.model_dump_json())
    for key in ("name", "function", "args", "content", "status"):
        assert key in payload


@pytest.mark.asyncio
async def test_event_mapper_keeps_browser_direct_url():
    event = ToolEvent(
        tool_call_id="call_browser_1",
        tool_name="browser",
        function_name="browser_click",
        function_args={"selector": "#submit"},
        status=ToolStatus.CALLED,
        function_result={"ok": True},
        tool_content=BrowserToolContent(screenshot="https://example.com/snap.png"),
    )

    sse_event = await EventMapper.event_to_sse_event(event)
    assert isinstance(sse_event, ToolSSEEvent)
    assert sse_event.data.content is not None
    assert sse_event.data.content.screenshot == "https://example.com/snap.png"
