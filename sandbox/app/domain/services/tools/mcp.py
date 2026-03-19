from __future__ import annotations

from typing import Any, Dict

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit
from app.services.runtime_mcp import runtime_mcp_service


class MCPToolkit(BaseToolkit):
    name: str = "mcp"

    @tool(parse_docstring=True)
    async def mcp_call(self, function_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Call MCP tool by function name.

        Args:
            function_name: MCP tool function name, e.g. mcp_server_tool.
            arguments: MCP tool arguments object.
        """
        result = await runtime_mcp_service.call(function_name=function_name, function_args=arguments or {})
        return ToolResult(**result)
