import asyncio
import logging
from typing import Any, Optional, List

from browser_use.browser.session import BrowserSession, CDPSession
from browser_use.dom.views import EnhancedDOMTreeNode

from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class BrowserUseBrowser:
    """Browser implementation using browser_use (aligned with source backend)."""

    def __init__(self, cdp_url: str):
        self.cdp_url = cdp_url
        self._session: Optional[BrowserSession] = None

    async def _ensure_session(self) -> BrowserSession:
        if self._session is not None:
            return self._session

        max_retries = 5
        retry_delay = 1.0
        last_error: Exception = RuntimeError("Unknown error")

        for attempt in range(max_retries):
            try:
                session = BrowserSession(
                    cdp_url=self.cdp_url,
                    minimum_wait_page_load_time=0.5,
                    wait_for_network_idle_page_load_time=2.0,
                    highlight_elements=False,
                )
                await session.start()
                self._session = session
                return session
            except Exception as exc:
                last_error = exc
                await self.cleanup()
                if attempt == max_retries - 1:
                    logger.error(
                        "Failed to initialise BrowserSession after %d attempts: %s",
                        max_retries,
                        exc,
                    )
                    raise
                retry_delay = min(retry_delay * 2, 10.0)
                logger.warning(
                    "BrowserSession init failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    retry_delay,
                    exc,
                )
                await asyncio.sleep(retry_delay)

        raise last_error

    async def cleanup(self) -> None:
        if self._session is not None:
            try:
                await self._session.stop()
            except Exception as exc:
                logger.error("Error stopping BrowserSession: %s", exc)
            finally:
                self._session = None

    async def _get_current_page(self):
        session = await self._ensure_session()
        page = await session.get_current_page()
        if page is None:
            page = await session.new_page()
        return page

    async def _get_cdp_session(self) -> CDPSession:
        session = await self._ensure_session()
        return await session.get_or_create_cdp_session()

    async def _get_interactive_elements(self) -> List[str]:
        try:
            session = await self._ensure_session()
            selector_map: dict[int, EnhancedDOMTreeNode] = await session.get_selector_map()
            formatted: List[str] = []
            for idx, node in sorted(selector_map.items()):
                tag = node.tag_name or "element"
                text = node.get_meaningful_text_for_llm() if hasattr(node, "get_meaningful_text_for_llm") else ""
                if not text and node.attributes:
                    text = (
                        node.attributes.get("placeholder", "")
                        or node.attributes.get("aria-label", "")
                        or node.attributes.get("title", "")
                        or ""
                    )
                if len(text) > 100:
                    text = text[:97] + "..."
                formatted.append(f"{idx}:<{tag}>{text}</{tag}>")
            return formatted
        except Exception as exc:
            logger.warning("Failed to get interactive elements: %s", exc)
            return []

    async def _dispatch_mouse_event(
        self,
        event_type: str,
        x: float,
        y: float,
        button: str = "none",
        click_count: int = 0,
    ) -> None:
        cdp_sess = await self._get_cdp_session()
        params: dict[str, Any] = {
            "type": event_type,
            "x": x,
            "y": y,
            "button": button,
            "clickCount": click_count,
        }
        await cdp_sess.cdp_client.send.Input.dispatchMouseEvent(
            params=params,
            session_id=str(cdp_sess.session_id),
        )

    async def view_page(self) -> ToolResult:
        try:
            session = await self._ensure_session()
            state = await session.get_browser_state_summary(include_screenshot=False)
            interactive_elements = await self._get_interactive_elements()
            content = ""
            if state.dom_state is not None:
                content = state.dom_state.llm_representation()
            return ToolResult(
                success=True,
                data={"interactive_elements": interactive_elements, "content": content},
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to view page: {exc}")

    async def navigate(self, url: str) -> ToolResult:
        try:
            session = await self._ensure_session()
            await session.navigate_to(url)
            interactive_elements = await self._get_interactive_elements()
            return ToolResult(success=True, data={"interactive_elements": interactive_elements})
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to navigate to {url}: {exc}")

    async def restart(self, url: str) -> ToolResult:
        await self.cleanup()
        return await self.navigate(url)

    async def click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        try:
            if coordinate_x is not None and coordinate_y is not None:
                await self._dispatch_mouse_event("mousePressed", coordinate_x, coordinate_y, "left", 1)
                await self._dispatch_mouse_event("mouseReleased", coordinate_x, coordinate_y, "left", 1)
            elif index is not None:
                session = await self._ensure_session()
                node = await session.get_dom_element_by_index(index)
                if node is None:
                    return ToolResult(success=False, message=f"Cannot find interactive element with index {index}")
                page = await self._get_current_page()
                element = await page.get_element(node.backend_node_id)
                await element.click()
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to click element: {exc}")

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        try:
            page = await self._get_current_page()
            if coordinate_x is not None and coordinate_y is not None:
                await self._dispatch_mouse_event("mousePressed", coordinate_x, coordinate_y, "left", 1)
                await self._dispatch_mouse_event("mouseReleased", coordinate_x, coordinate_y, "left", 1)
                cdp_sess = await self._get_cdp_session()
                await cdp_sess.cdp_client.send.Input.insertText(
                    params={"text": text},
                    session_id=str(cdp_sess.session_id),
                )
            elif index is not None:
                session = await self._ensure_session()
                node = await session.get_dom_element_by_index(index)
                if node is None:
                    return ToolResult(success=False, message=f"Cannot find interactive element with index {index}")
                element = await page.get_element(node.backend_node_id)
                await element.fill(text)
            if press_enter:
                await page.press("Enter")
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to input text: {exc}")

    async def move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        try:
            await self._dispatch_mouse_event("mouseMoved", coordinate_x, coordinate_y)
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to move mouse: {exc}")

    async def press_key(self, key: str) -> ToolResult:
        try:
            page = await self._get_current_page()
            await page.press(key)
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to press key: {exc}")

    async def select_option(self, index: int, option: int) -> ToolResult:
        try:
            session = await self._ensure_session()
            node = await session.get_dom_element_by_index(index)
            if node is None:
                return ToolResult(success=False, message=f"Cannot find selector element with index {index}")
            page = await self._get_current_page()
            element = await page.get_element(node.backend_node_id)
            await element.select_option(str(option))
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to select option: {exc}")

    async def scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        try:
            page = await self._get_current_page()
            if to_top:
                await page.evaluate("() => window.scrollTo(0, 0)")
            else:
                await page.evaluate("() => window.scrollBy(0, -window.innerHeight)")
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to scroll up: {exc}")

    async def scroll_down(self, to_bottom: Optional[bool] = None) -> ToolResult:
        try:
            page = await self._get_current_page()
            if to_bottom:
                await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            else:
                await page.evaluate("() => window.scrollBy(0, window.innerHeight)")
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to scroll down: {exc}")

    async def screenshot(self, full_page: Optional[bool] = False) -> bytes:
        session = await self._ensure_session()
        return await session.take_screenshot(full_page=bool(full_page))

    async def console_exec(self, javascript: str) -> ToolResult:
        try:
            page = await self._get_current_page()
            js = javascript.strip()
            if not (js.startswith("(") and "=>" in js):
                js = f"() => {{ {js} }}"
            result = await page.evaluate(js)
            return ToolResult(success=True, data={"result": result})
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to execute JavaScript: {exc}")

    async def console_view(self, max_lines: Optional[int] = None) -> ToolResult:
        try:
            page = await self._get_current_page()
            logs_raw = await page.evaluate("() => window.console.logs || []")

            import json

            try:
                logs = json.loads(logs_raw) if isinstance(logs_raw, str) else logs_raw
            except (TypeError, ValueError):
                logs = logs_raw

            if max_lines is not None and isinstance(logs, list):
                logs = logs[-max_lines:]
            return ToolResult(success=True, data={"logs": logs})
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to view console: {exc}")


class RuntimeBrowserService:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self._browser = BrowserUseBrowser(cdp_url)
        self._lock = asyncio.Lock()

    @staticmethod
    def _to_payload(result: ToolResult) -> dict[str, Any]:
        return {
            "success": bool(result.success),
            "message": result.message or "",
            "data": result.data,
        }

    async def execute(self, function_name: str, function_args: dict[str, Any]) -> dict[str, Any]:
        fn = (function_name or "").strip()
        args = function_args or {}
        async with self._lock:
            if fn == "browser_view":
                return self._to_payload(await self._browser.view_page())
            if fn == "browser_navigate":
                return self._to_payload(await self._browser.navigate(str(args.get("url") or "").strip()))
            if fn == "browser_restart":
                return self._to_payload(await self._browser.restart(str(args.get("url") or "").strip()))
            if fn == "browser_click":
                return self._to_payload(
                    await self._browser.click(
                        index=args.get("index"),
                        coordinate_x=args.get("coordinate_x"),
                        coordinate_y=args.get("coordinate_y"),
                    )
                )
            if fn == "browser_input":
                return self._to_payload(
                    await self._browser.input(
                        text=str(args.get("text") or ""),
                        press_enter=bool(args.get("press_enter", False)),
                        index=args.get("index"),
                        coordinate_x=args.get("coordinate_x"),
                        coordinate_y=args.get("coordinate_y"),
                    )
                )
            if fn == "browser_move_mouse":
                return self._to_payload(
                    await self._browser.move_mouse(
                        coordinate_x=float(args.get("coordinate_x")),
                        coordinate_y=float(args.get("coordinate_y")),
                    )
                )
            if fn == "browser_press_key":
                return self._to_payload(await self._browser.press_key(str(args.get("key") or "")))
            if fn == "browser_select_option":
                return self._to_payload(
                    await self._browser.select_option(
                        index=int(args.get("index")),
                        option=int(args.get("option")),
                    )
                )
            if fn == "browser_scroll_down":
                return self._to_payload(await self._browser.scroll_down(to_bottom=bool(args.get("to_bottom", False))))
            if fn == "browser_scroll_up":
                return self._to_payload(await self._browser.scroll_up(to_top=bool(args.get("to_top", False))))
            if fn == "browser_console_exec":
                return self._to_payload(await self._browser.console_exec(str(args.get("javascript") or "")))
            if fn == "browser_console_view":
                max_lines = args.get("max_lines")
                return self._to_payload(
                    await self._browser.console_view(
                        max_lines=int(max_lines) if max_lines is not None else None
                    )
                )
            if fn == "browser_screenshot":
                image = await self._browser.screenshot(full_page=bool(args.get("full_page", False)))
                return {"success": True, "message": "", "data": {"bytes": image}}
            return {"success": False, "message": f"Unsupported browser function: {fn}", "data": {}}


runtime_browser_service = RuntimeBrowserService()
