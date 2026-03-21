from __future__ import annotations

from typing import Optional

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit
from app.domain.services.tools.local_api_client import local_sandbox_api_client


class ShellToolkit(BaseToolkit):
    name: str = "shell"

    @tool(parse_docstring=True)
    async def shell_exec(
        self,
        id: Optional[str] = None,
        exec_dir: str = "/home/ubuntu",
        command: str = "",
    ) -> ToolResult:
        """Execute shell command in a session.

        Args:
            id: Shell session id. If omitted, API will auto-create one.
            exec_dir: Absolute working directory.
            command: Command string.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/shell/exec",
            {"id": id or "", "exec_dir": exec_dir, "command": command},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_view(self, id: Optional[str] = None) -> ToolResult:
        """View shell session output.

        Args:
            id: Shell session id.
        """
        if not id:
            return ToolResult(success=False, message="id is required for shell_view")
        result = await local_sandbox_api_client.post("/api/v1/shell/view", {"id": id})
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_wait(self, id: Optional[str] = None, seconds: Optional[int] = None) -> ToolResult:
        """Wait for running process in shell session.

        Args:
            id: Shell session id.
            seconds: Optional wait seconds.
        """
        if not id:
            return ToolResult(success=False, message="id is required for shell_wait")
        result = await local_sandbox_api_client.post("/api/v1/shell/wait", {"id": id, "seconds": seconds})
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_write_to_process(
        self,
        id: Optional[str] = None,
        input: str = "",
        press_enter: bool = True,
    ) -> ToolResult:
        """Write input to process stdin.

        Args:
            id: Shell session id.
            input: Input text.
            press_enter: Whether to append Enter.
        """
        if not id:
            return ToolResult(success=False, message="id is required for shell_write_to_process")
        result = await local_sandbox_api_client.post(
            "/api/v1/shell/write",
            {"id": id, "input": input, "press_enter": press_enter},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_kill_process(self, id: Optional[str] = None) -> ToolResult:
        """Kill process in shell session.

        Args:
            id: Shell session id.
        """
        if not id:
            return ToolResult(success=False, message="id is required for shell_kill_process")
        result = await local_sandbox_api_client.post("/api/v1/shell/kill", {"id": id})
        return ToolResult(**result)
