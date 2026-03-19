from __future__ import annotations

from typing import Optional

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit
from app.services.runtime_browser import runtime_browser_service


class BrowserToolkit(BaseToolkit):
    name: str = "browser"

    async def _exec(self, function_name: str, function_args: dict) -> ToolResult:
        result = await runtime_browser_service.execute(function_name=function_name, function_args=function_args)
        return ToolResult(**result)

    @tool(parse_docstring=True)
    async def browser_view(self) -> ToolResult:
        """View current browser page."""
        return await self._exec("browser_view", {})

    @tool(parse_docstring=True)
    async def browser_navigate(self, url: str) -> ToolResult:
        """Navigate browser to URL.

        Args:
            url: Full URL with protocol.
        """
        return await self._exec("browser_navigate", {"url": url})

    @tool(parse_docstring=True)
    async def browser_click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Click element by index or coordinate.

        Args:
            index: Interactive element index.
            coordinate_x: X coordinate.
            coordinate_y: Y coordinate.
        """
        return await self._exec(
            "browser_click",
            {"index": index, "coordinate_x": coordinate_x, "coordinate_y": coordinate_y},
        )

    @tool(parse_docstring=True)
    async def browser_hover_observe(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Hover element and observe updated page.

        Args:
            index: Interactive element index.
            coordinate_x: X coordinate.
            coordinate_y: Y coordinate.
        """
        return await self._exec(
            "browser_hover_observe",
            {"index": index, "coordinate_x": coordinate_x, "coordinate_y": coordinate_y},
        )

    @tool(parse_docstring=True)
    async def browser_input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Input text to element.

        Args:
            text: Input text.
            press_enter: Press Enter after input.
            index: Interactive element index.
            coordinate_x: X coordinate.
            coordinate_y: Y coordinate.
        """
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

    @tool(parse_docstring=True)
    async def browser_press_key(self, key: str) -> ToolResult:
        """Press keyboard key.

        Args:
            key: Key name.
        """
        return await self._exec("browser_press_key", {"key": key})

    @tool(parse_docstring=True)
    async def browser_scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        """Scroll browser up.

        Args:
            to_top: Scroll to top directly.
        """
        return await self._exec("browser_scroll_up", {"to_top": to_top})

    @tool(parse_docstring=True)
    async def browser_scroll_down(self, to_bottom: Optional[bool] = None) -> ToolResult:
        """Scroll browser down.

        Args:
            to_bottom: Scroll to bottom directly.
        """
        return await self._exec("browser_scroll_down", {"to_bottom": to_bottom})

    @tool(parse_docstring=True)
    async def browser_console_exec(self, javascript: str) -> ToolResult:
        """Execute JavaScript in page context.

        Args:
            javascript: JavaScript source.
        """
        return await self._exec("browser_console_exec", {"javascript": javascript})

    @tool(parse_docstring=True)
    async def browser_wait_for_selector(
        self,
        selector: str,
        text_contains: Optional[str] = None,
        timeout_ms: Optional[int] = 6000,
    ) -> ToolResult:
        """Wait for selector to appear.

        Args:
            selector: CSS selector.
            text_contains: Optional text fragment.
            timeout_ms: Timeout in ms.
        """
        return await self._exec(
            "browser_wait_for_selector",
            {"selector": selector, "text_contains": text_contains, "timeout_ms": timeout_ms},
        )

    @tool(parse_docstring=True)
    async def browser_accessibility_snapshot(self, max_nodes: Optional[int] = 200) -> ToolResult:
        """Get accessibility snapshot.

        Args:
            max_nodes: Max node count.
        """
        return await self._exec("browser_accessibility_snapshot", {"max_nodes": max_nodes})
