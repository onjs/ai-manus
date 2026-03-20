from __future__ import annotations

import re
from typing import Optional

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit
from app.domain.services.tools.local_api_client import local_sandbox_api_client


class ShellToolkit(BaseToolkit):
    name: str = "shell"
    _WAIT_ONLY_PATTERN = re.compile(r"^\s*sleep\s+\d+(?:\.\d+)?\s*;?\s*$", re.IGNORECASE)

    @tool(parse_docstring=True)
    async def shell_exec(self, id: str, exec_dir: str, command: str) -> ToolResult:
        """Execute shell command in a session.

        Args:
            id: Shell session id.
            exec_dir: Absolute working directory.
            command: Command string.
        """
        if self._WAIT_ONLY_PATTERN.match(command or ""):
            return ToolResult(
                success=False,
                message=(
                    "shell_exec does not accept sleep-only waiting commands. "
                    "Use browser_wait_for_selector for browser/UI waiting."
                ),
            )
        result = await local_sandbox_api_client.post(
            "/api/v1/shell/exec",
            {"id": id, "exec_dir": exec_dir, "command": command},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_view(self, id: str) -> ToolResult:
        """View shell session output.

        Args:
            id: Shell session id.
        """
        result = await local_sandbox_api_client.post("/api/v1/shell/view", {"id": id})
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_wait(self, id: str, seconds: Optional[int] = None) -> ToolResult:
        """Wait for running process in shell session.

        Args:
            id: Shell session id.
            seconds: Optional wait seconds.
        """
        result = await local_sandbox_api_client.post("/api/v1/shell/wait", {"id": id, "seconds": seconds})
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_write_to_process(self, id: str, input: str, press_enter: bool) -> ToolResult:
        """Write input to process stdin.

        Args:
            id: Shell session id.
            input: Input text.
            press_enter: Whether to append Enter.
        """
        result = await local_sandbox_api_client.post(
            "/api/v1/shell/write",
            {"id": id, "input": input, "press_enter": press_enter},
        )
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def shell_kill_process(self, id: str) -> ToolResult:
        """Kill process in shell session.

        Args:
            id: Shell session id.
        """
        result = await local_sandbox_api_client.post("/api/v1/shell/kill", {"id": id})
        return ToolResult(**result)
