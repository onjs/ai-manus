from __future__ import annotations

from typing import Any, Dict, Optional

from langchain.tools import tool

from app.domain.external.browser import Browser
from app.domain.models.tool_result import ToolResult
from app.domain.services.browser_engine import BrowserEngine
from app.domain.services.tools.base import BaseToolkit
from app.services.runtime_browser import runtime_browser_service


class RuntimeBrowserAdapter(Browser):
    """Adapter that maps Browser protocol calls to runtime browser service."""

    async def _exec(self, function_name: str, function_args: Dict[str, Any]) -> ToolResult:
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

    async def hover(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        return await self._exec(
            "browser_hover_observe",
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

    async def wait_for_selector(
        self,
        selector: str,
        text_contains: Optional[str] = None,
        timeout_ms: Optional[int] = 6000,
    ) -> ToolResult:
        return await self._exec(
            "browser_wait_for_selector",
            {"selector": selector, "text_contains": text_contains, "timeout_ms": timeout_ms},
        )

    async def accessibility_snapshot(self, max_nodes: Optional[int] = 200) -> ToolResult:
        return await self._exec("browser_accessibility_snapshot", {"max_nodes": max_nodes})


class BrowserToolkit(BaseToolkit):
    """Browser toolkit, aligned with main branch browser behavior."""

    name: str = "browser"

    def __init__(self, model_kwargs: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.browser = RuntimeBrowserAdapter()
        self.browser_engine = BrowserEngine(self.browser, model_kwargs=model_kwargs)

    @tool(parse_docstring=True)
    async def browser_view(self) -> ToolResult:
        """View content of the current browser page. Use for checking the latest state of previously opened pages.
        """
        return await self.browser.view_page()

    @tool(parse_docstring=True)
    async def browser_navigate(self, url: str) -> ToolResult:
        """Navigate browser to specified URL. Use when accessing new pages is needed.

        Args:
            url: Complete URL to visit. Must include protocol prefix.
        """
        return await self.browser.navigate(url)

    @tool(parse_docstring=True)
    async def browser_restart(self, url: str) -> ToolResult:
        """Restart browser and navigate to specified URL. Use when browser state needs to be reset.

        Args:
            url: Complete URL to visit after restart. Must include protocol prefix.
        """
        return await self.browser.restart(url)

    @tool(parse_docstring=True)
    async def browser_click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None
    ) -> ToolResult:
        """Click on elements in the current browser page. Use when clicking page elements is needed.

        Args:
            index: (Optional) Index number of the element to click
            coordinate_x: (Optional) X coordinate of click position
            coordinate_y: (Optional) Y coordinate of click position
        """
        return await self.browser.click(index, coordinate_x, coordinate_y)

    @tool(parse_docstring=True)
    async def browser_hover_observe(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None
    ) -> ToolResult:
        """Hover on an element and re-observe page state. Use before clicking dynamic dropdown/menu items.

        Args:
            index: (Optional) Index number of the element to hover
            coordinate_x: (Optional) X coordinate to hover
            coordinate_y: (Optional) Y coordinate to hover
        """
        return await self.browser.hover(index, coordinate_x, coordinate_y)

    @tool(parse_docstring=True)
    async def browser_input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None
    ) -> ToolResult:
        """Overwrite text in editable elements on the current browser page. Use when filling content in input fields.

        Args:
            index: (Optional) Index number of the element to overwrite text
            coordinate_x: (Optional) X coordinate of the element to overwrite text
            coordinate_y: (Optional) Y coordinate of the element to overwrite text
            text: Complete text content to overwrite
            press_enter: Whether to press Enter key after input
        """
        return await self.browser.input(text, press_enter, index, coordinate_x, coordinate_y)

    @tool(parse_docstring=True)
    async def browser_set_date_field(
        self,
        field_label: str,
        date_expr: str = "today"
    ) -> ToolResult:
        """Set a date/time-like form field by semantic label. Use for enterprise date picker fields.

        Args:
            field_label: Human-readable label of the field (e.g., "计划开始时间").
            date_expr: Date expression such as today/tomorrow/next_week/next_monday/YYYY-MM-DD.
        """
        return await self.browser_engine.set_date_field(field_label=field_label, date_expr=date_expr)

    @tool(parse_docstring=True)
    async def browser_set_select_field(
        self,
        field_label: str,
        field_value: str
    ) -> ToolResult:
        """Select a dropdown/combobox field by semantic label and option text.

        Args:
            field_label: Human-readable label of the field.
            field_value: Option text/value to choose.
        """
        return await self.browser_engine.set_select_field(field_label=field_label, field_value=field_value)

    @tool(parse_docstring=True)
    async def browser_set_people_field(
        self,
        field_label: str,
        field_value: str
    ) -> ToolResult:
        """Fill a people/assignee-like field by semantic label.

        Args:
            field_label: Human-readable label of the field.
            field_value: Person name/account identifier to input.
        """
        return await self.browser_engine.set_people_field(field_label=field_label, field_value=field_value)

    @tool(parse_docstring=True)
    async def browser_move_mouse(
        self,
        coordinate_x: float,
        coordinate_y: float
    ) -> ToolResult:
        """Move cursor to specified position on the current browser page. Use when simulating user mouse movement.

        Args:
            coordinate_x: X coordinate of target cursor position
            coordinate_y: Y coordinate of target cursor position
        """
        return await self.browser.move_mouse(coordinate_x, coordinate_y)

    @tool(parse_docstring=True)
    async def browser_press_key(
        self,
        key: str
    ) -> ToolResult:
        """Simulate key press in the current browser page. Use when specific keyboard operations are needed.

        Args:
            key: Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter).
        """
        return await self.browser.press_key(key)

    @tool(parse_docstring=True)
    async def browser_select_option(
        self,
        index: int,
        option: int
    ) -> ToolResult:
        """Select specified option from dropdown list element in the current browser page. Use when selecting dropdown menu options.

        Args:
            index: Index number of the dropdown list element
            option: Option number to select, starting from 0.
        """
        return await self.browser.select_option(index, option)

    @tool(parse_docstring=True)
    async def browser_scroll_up(
        self,
        to_top: Optional[bool] = None
    ) -> ToolResult:
        """Scroll up the current browser page. Use when viewing content above or returning to page top.

        Args:
            to_top: (Optional) Whether to scroll directly to page top instead of one viewport up.
        """
        return await self.browser.scroll_up(to_top)

    @tool(parse_docstring=True)
    async def browser_scroll_down(
        self,
        to_bottom: Optional[bool] = None
    ) -> ToolResult:
        """Scroll down the current browser page. Use when viewing content below or jumping to page bottom.

        Args:
            to_bottom: (Optional) Whether to scroll directly to page bottom instead of one viewport down.
        """
        return await self.browser.scroll_down(to_bottom)

    @tool(parse_docstring=True)
    async def browser_console_exec(
        self,
        javascript: str
    ) -> ToolResult:
        """Execute JavaScript code in browser console. Use when custom scripts need to be executed.

        Args:
            javascript: JavaScript code to execute. Note that the runtime environment is browser console.
        """
        return await self.browser.console_exec(javascript)

    @tool(parse_docstring=True)
    async def browser_console_view(
        self,
        max_lines: Optional[int] = None
    ) -> ToolResult:
        """View browser console output. Use when checking JavaScript logs or debugging page errors.

        Args:
            max_lines: (Optional) Maximum number of log lines to return.
        """
        return await self.browser.console_view(max_lines)

    @tool(parse_docstring=True)
    async def browser_wait_for_selector(
        self,
        selector: str,
        text_contains: Optional[str] = None,
        timeout_ms: Optional[int] = 6000
    ) -> ToolResult:
        """Wait for a selector to appear and optionally verify text. Use for post-action verification.

        Args:
            selector: CSS selector to wait for.
            text_contains: (Optional) Expected text fragment inside the matched element.
            timeout_ms: (Optional) Max wait time in milliseconds.
        """
        return await self.browser.wait_for_selector(selector, text_contains, timeout_ms)

    @tool(parse_docstring=True)
    async def browser_accessibility_snapshot(
        self,
        max_nodes: Optional[int] = 200
    ) -> ToolResult:
        """Get accessibility tree snapshot (role/name/state) for robust dynamic-page decisions.

        Args:
            max_nodes: (Optional) Maximum number of nodes returned.
        """
        return await self.browser.accessibility_snapshot(max_nodes)

    @tool(parse_docstring=True)
    async def browser_run_goal(
        self,
        goal: str,
        expected_result: Optional[str] = None,
        extra_context: Optional[str] = None,
        max_steps: Optional[int] = 12,
        task_timeout_seconds: Optional[int] = 300
    ) -> ToolResult:
        """Run a complete browser subtask with unified decision layer.

        This tool is preferred for multi-step browser jobs, dynamic menus, and complex forms.

        Args:
            goal: Natural language goal to complete in the browser.
            expected_result: (Optional) Specific success expectation for verification.
            extra_context: (Optional) Structured hints such as form data or constraints.
            max_steps: (Optional) Maximum decision rounds.
            task_timeout_seconds: (Optional) Timeout for this browser subtask.
        """
        return await self.browser_engine.execute_goal(
            goal=goal,
            expected_result=expected_result,
            extra_context=extra_context,
            max_steps=max(1, min(max_steps or 12, 48)),
            task_timeout_seconds=max(30, min(task_timeout_seconds or 300, 1800)),
        )
