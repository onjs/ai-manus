from __future__ import annotations

from typing import Optional

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit
from app.services.runtime_search import runtime_search_service


class SearchToolkit(BaseToolkit):
    name: str = "search"

    @tool(parse_docstring=True)
    async def info_search_web(self, query: str, date_range: Optional[str] = None) -> ToolResult:
        """Search web content.

        Args:
            query: Search query.
            date_range: Optional date range.
        """
        result = await runtime_search_service.search_web(query=query, date_range=date_range)
        return ToolResult(**result)
