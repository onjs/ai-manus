from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from app.domain.external.browser import Browser
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import AgentEvent, ErrorEvent
from app.domain.models.message import Message
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.tools.mcp import MCPToolkit
from app.infrastructure.repositories.in_memory_agent_repository import in_memory_agent_repository
from app.infrastructure.repositories.runtime_session_repository import runtime_session_repository
from app.services.file import file_service
from app.services.runtime import RuntimeService
from app.services.runtime_browser import runtime_browser_service
from app.services.runtime_search import runtime_search_service
from app.services.shell import shell_service


class RuntimeBrowserAdapter(Browser):
    async def _exec(self, function_name: str, function_args: dict[str, Any]) -> ToolResult:
        result = await runtime_browser_service.execute(function_name=function_name, function_args=function_args)
        return ToolResult(**result)

    async def view_page(self) -> ToolResult:
        return await self._exec("browser_view", {})

    async def navigate(self, url: str) -> ToolResult:
        return await self._exec("browser_navigate", {"url": url})

    async def restart(self, url: str) -> ToolResult:
        return await self._exec("browser_restart", {"url": url})

    async def click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        return await self._exec(
            "browser_click",
            {"index": index, "coordinate_x": coordinate_x, "coordinate_y": coordinate_y},
        )

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        return await self._exec(
            "browser_input",
            {
                "text": text,
                "press_enter": press_enter,
                "index": index,
                "coordinate_x": coordinate_x,
                "coordinate_y": coordinate_y,
            },
        )

    async def move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        return await self._exec("browser_move_mouse", {"coordinate_x": coordinate_x, "coordinate_y": coordinate_y})

    async def press_key(self, key: str) -> ToolResult:
        return await self._exec("browser_press_key", {"key": key})

    async def select_option(self, index: int, option: int) -> ToolResult:
        return await self._exec("browser_select_option", {"index": index, "option": option})

    async def scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        return await self._exec("browser_scroll_up", {"to_top": to_top})

    async def scroll_down(self, to_bottom: Optional[bool] = None) -> ToolResult:
        return await self._exec("browser_scroll_down", {"to_bottom": to_bottom})

    async def screenshot(self, full_page: Optional[bool] = False) -> bytes:
        result = await self._exec("browser_screenshot", {"full_page": bool(full_page)})
        if not result.success:
            raise RuntimeError(result.message or "browser_screenshot failed")
        data = result.data if isinstance(result.data, dict) else {}
        screenshot = data.get("bytes")
        if isinstance(screenshot, bytes):
            return screenshot
        raise RuntimeError("browser_screenshot returned invalid payload")

    async def console_exec(self, javascript: str) -> ToolResult:
        return await self._exec("browser_console_exec", {"javascript": javascript})

    async def console_view(self, max_lines: Optional[int] = None) -> ToolResult:
        return await self._exec("browser_console_view", {"max_lines": max_lines})


class RuntimeSandboxAdapter(Sandbox):
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
        return RuntimeBrowserAdapter()


class RuntimeSearchAdapter(SearchEngine):
    async def search(self, query: str, date_range: Optional[str] = None) -> ToolResult:
        result = await runtime_search_service.search_web(query=query, date_range=date_range)
        return ToolResult(**result)


class RuntimeAgentService:
    """LangChain-based runtime agent service (planner + execution + memory)."""

    def __init__(self, gateway_runtime: RuntimeService):
        self._gateway_runtime = gateway_runtime
        self._agent_repository = in_memory_agent_repository

    def _build_flow(self, *, session_id: str, agent_id: str) -> PlanActFlow:
        model_kwargs = self._gateway_runtime.get_chat_model_kwargs(session_id)
        return PlanActFlow(
            agent_id=agent_id,
            agent_repository=self._agent_repository,
            session_id=session_id,
            session_repository=runtime_session_repository,
            sandbox=RuntimeSandboxAdapter(),
            browser=RuntimeBrowserAdapter(),
            mcp_tool=MCPToolkit(),
            search_engine=RuntimeSearchAdapter(),
            model_kwargs=model_kwargs,
        )

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
                yield self._map_event(event)
        except Exception as e:
            err = ErrorEvent(error=str(e))
            yield self._map_event(err)
