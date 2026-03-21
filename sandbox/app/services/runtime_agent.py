from __future__ import annotations

import base64
import logging
from typing import Any, AsyncGenerator, Optional

from app.domain.external.browser import Browser
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import AgentEvent, BrowserToolContent, ErrorEvent, ToolEvent, ToolStatus
from app.domain.models.message import Message
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.tools.mcp import MCPToolkit
from app.core.config import settings
from app.infrastructure.external.browser.browser_use_browser import BrowserUseBrowser
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser
from app.infrastructure.repositories.in_memory_agent_repository import in_memory_agent_repository
from app.infrastructure.repositories.runtime_session_repository import runtime_session_repository
from app.services.file import file_service
from app.services.runtime import RuntimeService
from app.services.runtime_search import runtime_search_service
from app.services.shell import shell_service

logger = logging.getLogger(__name__)


class RuntimeSandboxAdapter(Sandbox):
    def __init__(self, browser: Browser):
        self._browser = browser

    async def ensure_sandbox(self) -> None:
        return None

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        result = await shell_service.exec_command(session_id=session_id, exec_dir=exec_dir, command=command)
        return ToolResult(success=True, message="Command executed", data=result.model_dump())

    async def view_shell(self, session_id: str, console: bool = False) -> ToolResult:
        result = await shell_service.view_shell(session_id=session_id, console=console)
        return ToolResult(success=True, message="Session content retrieved successfully", data=result.model_dump())

    async def wait_for_process(self, session_id: str, seconds: Optional[int] = None) -> ToolResult:
        result = await shell_service.wait_for_process(session_id=session_id, seconds=seconds)
        return ToolResult(
            success=True,
            message=f"Process completed, return code: {result.returncode}",
            data=result.model_dump(),
        )

    async def write_to_process(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        result = await shell_service.write_to_process(
            session_id=session_id,
            input_text=input_text,
            press_enter=press_enter,
        )
        return ToolResult(success=True, message="Input written", data=result.model_dump())

    async def kill_process(self, session_id: str) -> ToolResult:
        result = await shell_service.kill_process(session_id=session_id)
        message = "Process terminated" if result.status == "terminated" else "Process ended"
        return ToolResult(success=True, message=message, data=result.model_dump())

    async def file_write(
        self,
        file: str,
        content: str,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> ToolResult:
        result = await file_service.write_file(
            file=file,
            content=content,
            append=append,
            leading_newline=leading_newline,
            trailing_newline=trailing_newline,
            sudo=sudo,
        )
        return ToolResult(success=True, message="File written successfully", data=result.model_dump())

    async def file_read(
        self,
        file: str,
        start_line: int = None,
        end_line: int = None,
        sudo: bool = False,
    ) -> ToolResult:
        result = await file_service.read_file(
            file=file,
            start_line=start_line,
            end_line=end_line,
            sudo=sudo,
        )
        return ToolResult(success=True, message="File read successfully", data=result.model_dump())

    async def file_exists(self, path: str) -> ToolResult:
        try:
            file_service.ensure_file(path)
            return ToolResult(success=True, message="File exists", data={"path": path, "exists": True})
        except Exception:
            return ToolResult(success=True, message="File not found", data={"path": path, "exists": False})

    async def file_delete(self, path: str) -> ToolResult:
        raise NotImplementedError("file_delete is not implemented in sandbox runtime")

    async def file_list(self, path: str) -> ToolResult:
        raise NotImplementedError("file_list is not implemented in sandbox runtime")

    async def file_replace(self, file: str, old_str: str, new_str: str, sudo: bool = False) -> ToolResult:
        result = await file_service.str_replace(file=file, old_str=old_str, new_str=new_str, sudo=sudo)
        return ToolResult(
            success=True,
            message=f"Replacement completed, replaced {result.replaced_count} occurrences",
            data=result.model_dump(),
        )

    async def file_search(self, file: str, regex: str, sudo: bool = False) -> ToolResult:
        result = await file_service.find_in_content(file=file, regex=regex, sudo=sudo)
        return ToolResult(
            success=True,
            message=f"Search completed, found {len(result.matches)} matches",
            data=result.model_dump(),
        )

    async def file_find(self, path: str, glob_pattern: str) -> ToolResult:
        result = await file_service.find_by_name(path=path, glob_pattern=glob_pattern)
        return ToolResult(
            success=True,
            message=f"Search completed, found {len(result.files)} files",
            data=result.model_dump(),
        )

    async def file_upload(self, file_data, path: str, filename: str = None) -> ToolResult:
        raise NotImplementedError("file_upload is not implemented in sandbox runtime")

    async def file_download(self, path: str):
        raise NotImplementedError("file_download is not implemented in sandbox runtime")

    async def destroy(self) -> bool:
        return False

    async def get_browser(self) -> Browser:
        return self._browser


class RuntimeSearchAdapter(SearchEngine):
    async def search(self, query: str, date_range: Optional[str] = None) -> ToolResult:
        result = await runtime_search_service.search_web(query=query, date_range=date_range)
        return ToolResult(**result)


class RuntimeAgentService:
    """LangChain-based runtime agent service (planner + execution + memory)."""

    def __init__(self, gateway_runtime: RuntimeService):
        self._gateway_runtime = gateway_runtime
        self._agent_repository = in_memory_agent_repository
        self._browser: Browser = self._create_browser()

    @staticmethod
    def _create_browser() -> Browser:
        cdp_url = "http://127.0.0.1:9222"
        engine = (settings.BROWSER_ENGINE or "playwright").strip().lower()
        if engine == "browser_use":
            logger.info("Runtime agent using BrowserUseBrowser (%s)", cdp_url)
            return BrowserUseBrowser(cdp_url)
        logger.info("Runtime agent using PlaywrightBrowser (%s)", cdp_url)
        return PlaywrightBrowser(cdp_url)

    def _build_flow(self, *, session_id: str, agent_id: str) -> PlanActFlow:
        model_kwargs = self._gateway_runtime.get_chat_model_kwargs(session_id)
        return PlanActFlow(
            agent_id=agent_id,
            agent_repository=self._agent_repository,
            session_id=session_id,
            session_repository=runtime_session_repository,
            sandbox=RuntimeSandboxAdapter(self._browser),
            browser=self._browser,
            mcp_tool=MCPToolkit(),
            search_engine=RuntimeSearchAdapter(),
            model_kwargs=model_kwargs,
        )

    async def _enrich_tool_event(self, event: AgentEvent) -> AgentEvent:
        if not isinstance(event, ToolEvent):
            return event
        if event.tool_name != "browser" or event.status != ToolStatus.CALLED:
            return event
        if event.tool_content is not None:
            return event

        try:
            image_bytes = await self._browser.screenshot(full_page=False)
            screenshot = f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"
            return event.model_copy(update={"tool_content": BrowserToolContent(screenshot=screenshot)})
        except Exception as exc:
            logger.warning("Failed to capture browser screenshot for tool event: %s", exc)
            return event

    @classmethod
    def _map_event(cls, event: AgentEvent) -> tuple[str, dict[str, Any]]:
        payload = event.model_dump(mode="json")
        payload["type"] = event.type
        return event.type, payload

    async def run(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str,
        sandbox_id: str,
        user_message: str,
        attachments: list[str] | None,
        session_status: str,
        last_plan: dict[str, Any] | None,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        _ = (user_id, sandbox_id)
        try:
            await runtime_session_repository.seed(
                session_id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                sandbox_id=sandbox_id,
                status=session_status,
                last_plan=last_plan,
            )
            flow = self._build_flow(session_id=session_id, agent_id=agent_id)
            async for event in flow.run(Message(message=user_message, attachments=list(attachments or []))):
                event = await self._enrich_tool_event(event)
                yield self._map_event(event)
        except Exception as e:
            err = ErrorEvent(error=str(e))
            yield self._map_event(err)
