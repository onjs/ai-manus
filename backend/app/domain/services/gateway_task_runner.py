import asyncio
import base64
import os
import re
import time
import logging
from typing import AsyncGenerator, Optional

from pydantic import TypeAdapter

from app.domain.external.file import FileStorage
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
    TitleEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.session import SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.domain.models.file import FileInfo
from app.infrastructure.external.gateway.client import GatewayClient, GatewayIssuedToken, GatewayStreamEvent

logger = logging.getLogger(__name__)
SANDBOX_PATH_RE = re.compile(r"/home/ubuntu/[^\s)\]}>\"']+")
BROWSER_DATA_URI_PREFIX = "data:image/"


class GatewayTaskRunner(TaskRunner):
    """Task runner delegating planning/execution to gateway runtime."""

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        sandbox: Sandbox,
        session_repository: SessionRepository,
        file_storage: FileStorage,
        gateway_client: GatewayClient,
    ):
        self._session_id = session_id
        self._agent_id = agent_id
        self._user_id = user_id
        self._sandbox = sandbox
        self._session_repository = session_repository
        self._file_storage = file_storage
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

    async def _build_tool_content(
        self,
        *,
        tool_name: str,
        tool_status: ToolStatus,
        function_args: dict,
        function_result: object,
    ) -> Optional[BrowserToolContent | SearchToolContent | ShellToolContent | FileToolContent | McpToolContent]:
        payload = self._unwrap_result_data(function_result)

        if tool_name == "browser":
            if isinstance(payload, dict):
                for key in ("screenshot", "screenshot_url", "image_url", "image", "snapshot"):
                    screenshot = payload.get(key)
                    if isinstance(screenshot, str) and screenshot.strip():
                        screenshot_ref = await self._normalize_browser_screenshot_ref(screenshot)
                        return BrowserToolContent(screenshot=screenshot_ref)
            return None

        if tool_name == "search":
            if isinstance(payload, dict):
                results = payload.get("results")
                if isinstance(results, list):
                    return SearchToolContent(results=self._normalize_search_results(results))
            return None

        if tool_name == "shell":
            shell_session_id = self._extract_shell_session_id(function_args, function_result)
            # Keep shell snapshot format aligned with main: fetch console records (includes ps1 prompt).
            if tool_status == ToolStatus.CALLED and shell_session_id:
                try:
                    shell_result = await self._sandbox.view_shell(shell_session_id, console=True)
                    if shell_result.success and isinstance(shell_result.data, dict) and "console" in shell_result.data:
                        return ShellToolContent(console=shell_result.data.get("console"))
                except Exception:
                    pass
            if isinstance(payload, dict):
                if "console" in payload:
                    return ShellToolContent(console=payload.get("console"))
                # Persist a replay-friendly snapshot for shell_exec-like results.
                command = payload.get("command")
                output = payload.get("output")
                if isinstance(command, str):
                    return ShellToolContent(
                        console=[
                            {
                                "ps1": "ubuntu@sandbox:~ $",
                                "command": command,
                                "output": output if isinstance(output, str) else str(output or ""),
                            }
                        ]
                    )
            return None

        if tool_name == "file":
            if tool_status == ToolStatus.CALLED:
                if "file" in function_args:
                    file_path = function_args["file"]
                    file_read_result = await self._sandbox.file_read(file_path)
                    file_content = ""
                    if isinstance(file_read_result.data, dict):
                        file_content = file_read_result.data.get("content", "")
                    return FileToolContent(content=file_content)
                return FileToolContent(content="(No Content)")
            return None

        return McpToolContent(result=payload)

    async def _normalize_browser_screenshot_ref(self, screenshot: str) -> str:
        if not screenshot.startswith(BROWSER_DATA_URI_PREFIX):
            return screenshot

        if ";base64," not in screenshot:
            raise ValueError("Invalid browser screenshot data URI: missing base64 marker")

        header, encoded = screenshot.split(",", 1)
        image_format = "png"
        if "/" in header:
            image_format = header.split("/", 1)[1].split(";", 1)[0].strip() or "png"
        image_bytes = base64.b64decode(encoded, validate=True)
        filename = f"browser_screenshot.{image_format}"
        file_info = await self._file_storage.upload_file(image_bytes, filename, self._user_id)
        return file_info.file_id

    async def _normalize_tool_event(self, tool_event: ToolEvent) -> ToolEvent:
        normalized_args = self._normalize_function_args(
            tool_name=tool_event.tool_name,
            args=tool_event.function_args or {},
            function_result=tool_event.function_result,
        )
        tool_content = tool_event.tool_content
        if tool_content is None:
            tool_content = await self._build_tool_content(
                tool_name=tool_event.tool_name,
                tool_status=tool_event.status,
                function_args=normalized_args,
                function_result=tool_event.function_result,
            )
        elif isinstance(tool_content, BrowserToolContent):
            screenshot_ref = await self._normalize_browser_screenshot_ref(tool_content.screenshot)
            tool_content = BrowserToolContent(screenshot=screenshot_ref)
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

    async def _sync_file_to_storage(self, file_path: str) -> Optional[FileInfo]:
        """Upload or update sandbox file in persistent storage and return FileInfo."""
        try:
            file_info = await self._session_repository.get_file_by_path(self._session_id, file_path)
            file_data = await self._sandbox.file_download(file_path)
            if file_info and file_info.file_id:
                await self._session_repository.remove_file(self._session_id, file_info.file_id)
            file_name = file_path.split("/")[-1]
            file_info = await self._file_storage.upload_file(file_data, file_name, self._user_id)
            file_info.file_path = file_path
            await self._session_repository.add_file(self._session_id, file_info)
            return file_info
        except Exception as e:
            logger.exception(f"Session {self._session_id} failed to sync file {file_path}: {e}")
            return None

    async def _sync_file_to_sandbox(self, file_id: str) -> Optional[FileInfo]:
        """Download file from storage to sandbox and return FileInfo with sandbox path."""
        try:
            file_data, file_info = await self._file_storage.download_file(file_id, self._user_id)
            file_path = "/home/ubuntu/upload/" + str(file_info.filename)
            result = await self._sandbox.file_upload(file_data, file_path)
            if result.success:
                file_info.file_path = file_path
                return file_info
        except Exception as e:
            logger.exception(f"Session {self._session_id} failed to sync file {file_id} to sandbox: {e}")
        return None

    async def _sync_message_attachments_to_sandbox(self, event: MessageEvent) -> None:
        """Convert message attachments from file_id to sandbox file_path for runtime input."""
        attachments: list[FileInfo] = []
        if not event.attachments:
            event.attachments = attachments
            return
        for attachment in event.attachments:
            if attachment.file_path:
                attachments.append(attachment)
                continue
            if attachment.file_id:
                file_info = await self._sync_file_to_sandbox(attachment.file_id)
                if file_info:
                    attachments.append(file_info)
                    await self._ensure_session_file(file_info)
        event.attachments = attachments

    async def _ensure_session_file(self, file_info: FileInfo) -> None:
        if not file_info.file_id:
            return
        session = await self._session_repository.find_by_id(self._session_id)
        if session is not None and any(item.file_id == file_info.file_id for item in session.files):
            return
        await self._session_repository.add_file(self._session_id, file_info)

    @staticmethod
    def _sanitize_sandbox_paths(message: str) -> str:
        if not message:
            return message
        return SANDBOX_PATH_RE.sub(lambda m: os.path.basename(m.group(0)), message)

    async def _sync_message_attachments_to_storage(self, event: MessageEvent) -> None:
        """Convert message attachments from sandbox paths to storage-backed FileInfo."""
        attachments: list[FileInfo] = []
        if not event.attachments:
            event.attachments = attachments
            return
        for attachment in event.attachments:
            if attachment.file_id:
                await self._ensure_session_file(attachment)
                attachments.append(attachment)
                continue
            if attachment.file_path:
                file_info = await self._sync_file_to_storage(attachment.file_path)
                if file_info:
                    attachments.append(file_info)
        event.attachments = attachments

    async def _map_stream_event(
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
            event = await self._normalize_tool_event(event)

        stop = isinstance(event, (DoneEvent, ErrorEvent, WaitEvent))
        return [event], stop

    async def _run_gateway_flow(
        self,
        message: str,
        session_status: str,
        last_plan: Optional[dict] = None,
        attachments: Optional[list[str]] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        await self._ensure_gateway_runtime_configured()
        start_result = await self._sandbox.runtime_start_runner(
            session_id=self._session_id,
            agent_id=self._agent_id,
            user_id=self._user_id,
            sandbox_id=self._sandbox.id,
            message=message,
            attachments=attachments or [],
            session_status=session_status,
            last_plan=last_plan,
        )
        if not start_result.success:
            yield ErrorEvent(error=f"Failed to start sandbox runner: {start_result.message or 'unknown error'}")
            return
        await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)

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
                out_events, stop = await self._map_stream_event(stream_event)
                for out_event in out_events:
                    yield out_event
                if stop:
                    return
        except Exception as e:
            yield ErrorEvent(error=f"Sandbox runner stream interrupted: {e}")
            return

    async def run(self, task: Task) -> None:
        try:
            while not await task.input_stream.is_empty():
                event = await self._pop_event(task)
                if not event:
                    continue

                message = ""
                message_attachments: list[str] = []
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                    await self._sync_message_attachments_to_sandbox(event)
                    message_attachments = [
                        attachment.file_path
                        for attachment in (event.attachments or [])
                        if isinstance(attachment.file_path, str) and attachment.file_path.strip()
                    ]
                if not message:
                    await self._put_and_add_event(task, ErrorEvent(error="No message"))
                    continue

                session = await self._session_repository.find_by_id(self._session_id)
                if session is None:
                    await self._put_and_add_event(task, ErrorEvent(error="Session not found"))
                    return
                session_status = session.status.value if hasattr(session.status, "value") else str(session.status)
                plan = session.get_last_plan()
                last_plan = plan.model_dump(mode="json") if plan is not None else None

                async for out_event in self._run_gateway_flow(
                    message,
                    session_status=session_status,
                    last_plan=last_plan,
                    attachments=message_attachments,
                ):
                    status_value = (
                        out_event.status.value
                        if isinstance(out_event, ToolEvent) and hasattr(out_event.status, "value")
                        else str(getattr(out_event, "status", ""))
                    )
                    if (
                        isinstance(out_event, ToolEvent)
                        and out_event.tool_name == "file"
                        and status_value == ToolStatus.CALLED.value
                    ):
                        file_path = out_event.function_args.get("file")
                        if isinstance(file_path, str) and file_path.strip():
                            await self._sync_file_to_storage(file_path)
                    if isinstance(out_event, MessageEvent):
                        if out_event.role == "assistant":
                            out_event.message = self._sanitize_sandbox_paths(out_event.message)
                        await self._sync_message_attachments_to_storage(out_event)
                    await self._put_and_add_event(task, out_event)
                    if isinstance(out_event, MessageEvent):
                        await self._session_repository.update_latest_message(
                            self._session_id,
                            out_event.message,
                            out_event.timestamp,
                        )
                        await self._session_repository.increment_unread_message_count(self._session_id)
                    elif isinstance(out_event, TitleEvent):
                        await self._session_repository.update_title(self._session_id, out_event.title)
                    elif isinstance(out_event, ErrorEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
                        await self._cleanup_gateway_credentials("stream_failed")
                        return
                    elif isinstance(out_event, WaitEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.WAITING)
                        await self._cleanup_gateway_credentials("waiting")
                        return
                    # Keep behavior aligned with upstream AgentTaskRunner:
                    # if a new user message arrives while current flow is running,
                    # interrupt current flow and switch to next input event.
                    if not await task.input_stream.is_empty():
                        await self._cleanup_gateway_credentials("interrupted_by_new_input")
                        break

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
        _ = task
        # `run()` already performs explicit credential cleanup on every terminal path.
        # Avoid duplicate async cleanup here, which can race with a new resumed run.
        return

    async def destroy(self) -> None:
        await self._cleanup_gateway_credentials("destroy")
