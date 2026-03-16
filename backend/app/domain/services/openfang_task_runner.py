import asyncio
import logging
import uuid
from typing import AsyncGenerator, Dict, Optional

from pydantic import TypeAdapter

from app.domain.external.task import Task, TaskRunner
from app.domain.models.event import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    McpToolContent,
    MessageEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.session import SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.external.openfang.client import OpenFangClient, OpenFangStreamEvent

logger = logging.getLogger(__name__)


class OpenFangTaskRunner(TaskRunner):
    """Task runner that proxies message execution to OpenFang."""

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        session_repository: SessionRepository,
        openfang_client: OpenFangClient,
        configured_openfang_agent_id: Optional[str] = None,
    ):
        self._session_id = session_id
        self._agent_id = agent_id
        self._user_id = user_id
        self._session_repository = session_repository
        self._openfang_client = openfang_client
        self._openfang_agent_id = configured_openfang_agent_id
        self._tool_call_ids: Dict[str, str] = {}

    async def _put_and_add_event(self, task: Task, event: AgentEvent) -> None:
        event_id = await task.output_stream.put(event.model_dump_json())
        event.id = event_id
        await self._session_repository.add_event(self._session_id, event)

    async def _pop_event(self, task: Task) -> Optional[AgentEvent]:
        event_id, event_str = await task.input_stream.pop()
        if not event_str:
            return None
        event = TypeAdapter(AgentEvent).validate_json(event_str)
        event.id = event_id
        return event

    def _tool_call_id_for(self, function_name: str, create: bool = True) -> str:
        if function_name in self._tool_call_ids:
            return self._tool_call_ids[function_name]
        if not create:
            return ""
        tool_call_id = f"openfang_{uuid.uuid4().hex[:12]}"
        self._tool_call_ids[function_name] = tool_call_id
        return tool_call_id

    async def _ensure_openfang_agent(self) -> str:
        if self._openfang_agent_id:
            return self._openfang_agent_id

        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise RuntimeError(f"Session not found: {self._session_id}")

        session_agent_id = session.openfang_agent_id
        self._openfang_agent_id = await self._openfang_client.ensure_agent(
            configured_agent_id=session_agent_id,
            name=f"ai-manus-{self._session_id[:8]}",
        )
        if session.openfang_agent_id != self._openfang_agent_id:
            session.openfang_agent_id = self._openfang_agent_id
            await self._session_repository.save(session)
        return self._openfang_agent_id

    def _map_tool_event(self, event: OpenFangStreamEvent) -> Optional[ToolEvent]:
        if event.event == "tool_use":
            function_name = str(event.data.get("tool", "openfang_tool"))
            tool_call_id = self._tool_call_id_for(function_name, create=True)
            return ToolEvent(
                tool_call_id=tool_call_id,
                tool_name="mcp",
                function_name=function_name,
                function_args={},
                status=ToolStatus.CALLING,
            )
        if event.event == "tool_result":
            function_name = str(event.data.get("tool", "openfang_tool"))
            tool_call_id = self._tool_call_id_for(function_name, create=True)
            args = event.data.get("input") or {}
            if not isinstance(args, dict):
                args = {"input": args}
            payload = {"tool": function_name, "input": args}
            self._tool_call_ids.pop(function_name, None)
            return ToolEvent(
                tool_call_id=tool_call_id,
                tool_name="mcp",
                function_name=function_name,
                function_args=args,
                status=ToolStatus.CALLED,
                function_result=payload,
                tool_content=McpToolContent(result=payload),
            )
        return None

    async def _run_openfang_flow(self, message: str) -> AsyncGenerator[AgentEvent, None]:
        openfang_agent_id = await self._ensure_openfang_agent()
        chunks: list[str] = []
        usage_payload: Optional[dict] = None

        async for stream_event in self._openfang_client.stream_message(
            agent_id=openfang_agent_id,
            message=message,
        ):
            if stream_event.event == "chunk":
                chunk_text = stream_event.data.get("content")
                if isinstance(chunk_text, str) and chunk_text:
                    chunks.append(chunk_text)
                continue
            if stream_event.event == "done":
                usage = stream_event.data.get("usage")
                if isinstance(usage, dict):
                    usage_payload = usage
                continue

            tool_event = self._map_tool_event(stream_event)
            if tool_event:
                yield tool_event

        response_text = "".join(chunks).strip()
        if not response_text:
            response_text = "(OpenFang returned no text response)"
        yield MessageEvent(role="assistant", message=response_text)

        if usage_payload:
            yield ToolEvent(
                tool_call_id=f"openfang_usage_{uuid.uuid4().hex[:8]}",
                tool_name="mcp",
                function_name="openfang_usage",
                function_args={},
                status=ToolStatus.CALLED,
                function_result=usage_payload,
                tool_content=McpToolContent(result=usage_payload),
            )

        yield DoneEvent()

    async def run(self, task: Task) -> None:
        try:
            logger.info("OpenFang task started for agent %s", self._agent_id)
            await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)

            while not await task.input_stream.is_empty():
                event = await self._pop_event(task)
                if not event:
                    continue

                message = ""
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                if not message:
                    await self._put_and_add_event(task, ErrorEvent(error="No message"))
                    continue

                async for out_event in self._run_openfang_flow(message):
                    await self._put_and_add_event(task, out_event)
                    if isinstance(out_event, MessageEvent):
                        await self._session_repository.update_latest_message(
                            self._session_id,
                            out_event.message,
                            out_event.timestamp,
                        )
                        await self._session_repository.increment_unread_message_count(self._session_id)
                    elif isinstance(out_event, WaitEvent):
                        await self._session_repository.update_status(
                            self._session_id,
                            SessionStatus.WAITING,
                        )
                        return
                    if not await task.input_stream.is_empty():
                        break

            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
        except asyncio.CancelledError:
            await self._put_and_add_event(task, DoneEvent())
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
        except Exception as e:
            logger.exception("OpenFang task error for agent %s: %s", self._agent_id, e)
            await self._put_and_add_event(task, ErrorEvent(error=f"Task error: {e}"))
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)

    async def on_done(self, task: Task) -> None:
        logger.info("OpenFang task done for agent %s", self._agent_id)

    async def destroy(self) -> None:
        logger.info("Destroy OpenFang runner for agent %s", self._agent_id)
