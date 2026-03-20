import asyncio
import time
from typing import AsyncGenerator, Optional

from pydantic import TypeAdapter

from app.domain.external.sandbox import Sandbox
from app.domain.external.task import Task, TaskRunner
from app.domain.models.event import (
    AgentEvent,
    BrowserToolContent,
    DoneEvent,
    ErrorEvent,
    FileToolContent,
    McpToolContent,
    MessageEvent,
    WaitEvent,
    SearchToolContent,
    ShellToolContent,
    ToolEvent,
)
from app.domain.models.session import SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.external.gateway.client import GatewayClient, GatewayIssuedToken, GatewayStreamEvent


class GatewayTaskRunner(TaskRunner):
    """Task runner delegating planning/execution to gateway runtime."""

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        sandbox: Sandbox,
        session_repository: SessionRepository,
        gateway_client: GatewayClient,
    ):
        self._session_id = session_id
        self._agent_id = agent_id
        self._user_id = user_id
        self._sandbox = sandbox
        self._session_repository = session_repository
        self._gateway_client = gateway_client
        self._gateway_token: Optional[str] = None
        self._gateway_token_id: Optional[str] = None
        self._gateway_token_expire_at: Optional[int] = None
        self._gateway_scopes: list[str] = ["llm:stream"]

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

    @staticmethod
    def _unwrap_result_data(function_result: object) -> object:
        if isinstance(function_result, dict):
            data = function_result.get("data")
            if isinstance(data, dict):
                return data
        return function_result

    @staticmethod
    def _extract_shell_session_id(args: dict, function_result: object) -> Optional[str]:
        for key in ("id", "session_id", "shell_session_id", "shell_id"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value

        payload = GatewayTaskRunner._unwrap_result_data(function_result)
        if isinstance(payload, dict):
            for key in ("id", "session_id", "shell_session_id", "shell_id"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return None

    @staticmethod
    def _extract_file_path(args: dict, function_result: object) -> Optional[str]:
        for key in ("file", "path", "file_path", "filepath"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value

        payload = GatewayTaskRunner._unwrap_result_data(function_result)
        if isinstance(payload, dict):
            for key in ("file", "path", "file_path", "filepath"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return None

    @staticmethod
    def _extract_search_query(args: dict, function_result: object) -> Optional[str]:
        for key in ("query", "q", "keyword"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value

        payload = GatewayTaskRunner._unwrap_result_data(function_result)
        if isinstance(payload, dict):
            for key in ("query", "q", "keyword"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return None

    def _normalize_function_args(
        self,
        *,
        tool_name: str,
        args: dict,
        function_result: object,
    ) -> dict:
        normalized = dict(args)
        if tool_name == "shell":
            shell_session_id = self._extract_shell_session_id(normalized, function_result)
            if shell_session_id:
                normalized["id"] = shell_session_id
        if tool_name == "file":
            file_path = self._extract_file_path(normalized, function_result)
            if file_path:
                normalized["file"] = file_path
        if tool_name == "search":
            query = self._extract_search_query(normalized, function_result)
            if query:
                normalized["query"] = query
        return normalized

    @staticmethod
    def _normalize_search_results(results: list) -> list[dict]:
        normalized: list[dict] = []
        for item in results:
            if not isinstance(item, dict):
                normalized.append(
                    {
                        "title": str(item),
                        "link": "",
                        "snippet": "",
                    }
                )
                continue
            normalized.append(
                {
                    "title": str(item.get("title") or item.get("name") or ""),
                    "link": str(item.get("link") or item.get("url") or item.get("href") or ""),
                    "snippet": str(item.get("snippet") or item.get("content") or item.get("description") or ""),
                }
            )
        return normalized

    def _build_tool_content(
        self,
        *,
        tool_name: str,
        function_result: object,
    ) -> Optional[BrowserToolContent | SearchToolContent | ShellToolContent | FileToolContent | McpToolContent]:
        payload = self._unwrap_result_data(function_result)

        if tool_name == "browser":
            if isinstance(payload, dict):
                for key in ("screenshot", "screenshot_url", "image_url", "image", "snapshot"):
                    screenshot = payload.get(key)
                    if isinstance(screenshot, str) and screenshot.strip():
                        return BrowserToolContent(screenshot=screenshot)
            return None

        if tool_name == "search":
            if isinstance(payload, dict):
                results = payload.get("results")
                if isinstance(results, list):
                    return SearchToolContent(results=self._normalize_search_results(results))
            return None

        if tool_name == "shell":
            if isinstance(payload, dict) and "console" in payload:
                return ShellToolContent(console=payload.get("console"))
            return None

        if tool_name == "file":
            if isinstance(payload, dict):
                content = payload.get("content")
                if isinstance(content, str):
                    return FileToolContent(content=content)
            return None

        return McpToolContent(result=payload)

    def _normalize_tool_event(self, tool_event: ToolEvent) -> ToolEvent:
        normalized_args = self._normalize_function_args(
            tool_name=tool_event.tool_name,
            args=tool_event.function_args or {},
            function_result=tool_event.function_result,
        )
        tool_content = tool_event.tool_content
        if tool_content is None:
            tool_content = self._build_tool_content(
                tool_name=tool_event.tool_name,
                function_result=tool_event.function_result,
            )
        return tool_event.model_copy(
            update={
                "function_args": normalized_args,
                "tool_content": tool_content,
            }
        )

    async def _ensure_gateway_runtime_configured(self) -> None:
        now = int(time.time())
        if self._gateway_token and self._gateway_token_id and self._gateway_token_expire_at and self._gateway_token_expire_at > now + 30:
            return

        issued: GatewayIssuedToken = await self._gateway_client.issue_token(
            session_id=self._session_id,
            agent_id=self._agent_id,
            sandbox_id=self._sandbox.id,
            scopes=self._gateway_scopes,
        )
        self._gateway_token = issued.token
        self._gateway_token_id = issued.token_id
        self._gateway_token_expire_at = issued.expire_at
        self._gateway_scopes = issued.scopes

        await self._sandbox.runtime_configure_gateway(
            session_id=self._session_id,
            gateway_base_url=self._gateway_client.base_url,
            gateway_token=self._gateway_token,
            gateway_token_id=self._gateway_token_id,
            gateway_token_expire_at=self._gateway_token_expire_at,
            scopes=self._gateway_scopes,
        )

    async def _cleanup_gateway_credentials(self, reason: str) -> None:
        await self._sandbox.runtime_cancel_runner(self._session_id)
        await self._sandbox.runtime_clear_gateway(self._session_id)
        if self._gateway_token_id:
            await self._gateway_client.revoke_token(self._gateway_token_id, reason=reason)
        self._gateway_token = None
        self._gateway_token_id = None
        self._gateway_token_expire_at = None

    def _map_stream_event(
        self,
        stream_event: GatewayStreamEvent,
    ) -> tuple[list[AgentEvent], bool]:
        try:
            payload = dict(stream_event.data or {})
            payload["type"] = stream_event.event
            event = TypeAdapter(AgentEvent).validate_python(payload)
        except Exception as e:
            return [ErrorEvent(error=f"Invalid gateway event payload: {e}")], True

        if isinstance(event, ToolEvent):
            event = self._normalize_tool_event(event)

        stop = isinstance(event, (DoneEvent, ErrorEvent, WaitEvent))
        return [event], stop

    async def _run_gateway_flow(self, message: str) -> AsyncGenerator[AgentEvent, None]:
        await self._ensure_gateway_runtime_configured()
        start_result = await self._sandbox.runtime_start_runner(
            session_id=self._session_id,
            agent_id=self._agent_id,
            user_id=self._user_id,
            sandbox_id=self._sandbox.id,
            message=message,
        )
        if not start_result.success:
            yield ErrorEvent(error=f"Failed to start sandbox runner: {start_result.message or 'unknown error'}")
            return

        next_seq = 1
        try:
            async for bridge_event in self._sandbox.runtime_stream_runner_events(
                session_id=self._session_id,
                from_seq=next_seq,
                limit=200,
            ):
                if bridge_event.event == "heartbeat":
                    continue

                payload = bridge_event.data or {}
                seq_value = payload.get("seq")
                if not isinstance(seq_value, int):
                    raise ValueError(f"sandbox event missing required integer field: seq ({bridge_event.event})")
                seq = seq_value
                next_seq = max(next_seq, seq + 1)
                stream_event = GatewayStreamEvent(
                    event=bridge_event.event,
                    data={k: v for k, v in payload.items() if k not in {"seq", "timestamp", "session_id"}},
                )
                out_events, stop = self._map_stream_event(stream_event)
                for out_event in out_events:
                    yield out_event
                if stop:
                    return
        except Exception as e:
            yield ErrorEvent(error=f"Sandbox runner stream interrupted: {e}")
            return

    async def run(self, task: Task) -> None:
        try:
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

                async for out_event in self._run_gateway_flow(message):
                    await self._put_and_add_event(task, out_event)
                    if isinstance(out_event, MessageEvent):
                        await self._session_repository.update_latest_message(
                            self._session_id,
                            out_event.message,
                            out_event.timestamp,
                        )
                        await self._session_repository.increment_unread_message_count(self._session_id)
                    elif isinstance(out_event, ErrorEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
                        await self._cleanup_gateway_credentials("stream_failed")
                        return
                    elif isinstance(out_event, WaitEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.WAITING)
                        await self._cleanup_gateway_credentials("waiting")
                        return

            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
            await self._cleanup_gateway_credentials("stream_complete")
        except asyncio.CancelledError:
            await self._put_and_add_event(task, DoneEvent())
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
            await self._cleanup_gateway_credentials("cancelled")
        except Exception as e:
            await self._put_and_add_event(task, ErrorEvent(error=f"Task error: {e}"))
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
            await self._cleanup_gateway_credentials("stream_failed")

    async def on_done(self, task: Task) -> None:
        await self._cleanup_gateway_credentials("done")

    async def destroy(self) -> None:
        await self._cleanup_gateway_credentials("destroy")
