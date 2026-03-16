from typing import Any, Optional, List
import asyncio
import logging

from browser_use.browser.session import BrowserSession, CDPSession
from browser_use.dom.views import EnhancedDOMTreeNode

from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class BrowserUseBrowser:
    """Browser implementation using the browser_use library (BrowserSession + CDP).

    Connects to an existing Chrome instance via CDP URL and exposes the same
    interface as PlaywrightBrowser so it can be used as a drop-in replacement.
    """

    def __init__(self, cdp_url: str):
        self.cdp_url = cdp_url
        self._session: Optional[BrowserSession] = None
        self._max_content_chars = 12000
        self._max_interactive_elements = 160

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> BrowserSession:
        """Return a started BrowserSession, initialising it if necessary."""
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
        """Stop the browser session and release resources."""
        if self._session is not None:
            try:
                await self._session.stop()
            except Exception as exc:
                logger.error("Error stopping BrowserSession: %s", exc)
            finally:
                self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_current_page(self):
        """Return the actor Page for the currently focused tab."""
        session = await self._ensure_session()
        page = await session.get_current_page()
        if page is None:
            page = await session.new_page()
        return page

    async def _get_cdp_session(self) -> CDPSession:
        """Return the CDPSession for the currently focused tab."""
        session = await self._ensure_session()
        return await session.get_or_create_cdp_session()

    async def _get_interactive_elements(self) -> List[str]:
        """Return a formatted list of interactive elements from the DOM selector map."""
        try:
            session = await self._ensure_session()
            selector_map: dict[int, EnhancedDOMTreeNode] = await session.get_selector_map()
            formatted: List[str] = []
            for idx, node in sorted(selector_map.items()):
                if len(formatted) >= self._max_interactive_elements:
                    break
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

    @staticmethod
    def _node_text(node: EnhancedDOMTreeNode) -> str:
        text = node.get_meaningful_text_for_llm() if hasattr(node, "get_meaningful_text_for_llm") else ""
        if not text and node.attributes:
            text = (
                node.attributes.get("aria-label", "")
                or node.attributes.get("placeholder", "")
                or node.attributes.get("title", "")
                or node.attributes.get("name", "")
                or ""
            )
        return str(text).strip()

    async def _click_by_text_fallback(self, text: str) -> bool:
        """Fallback click for dynamic overlays where backend node ids become stale."""
        if not text:
            return False
        page = await self._get_current_page()
        escaped = text.replace("\\", "\\\\").replace("'", "\\'")

        return bool(
            await page.evaluate(
                f"""() => {{
                    const target = '{escaped}'.trim().toLowerCase();
                    if (!target) return false;

                    const isVisible = (el) => {{
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return false;
                        const style = window.getComputedStyle(el);
                        if (!style) return false;
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                        return true;
                    }};

                    const candidates = document.querySelectorAll(
                      '[role=\"menuitem\"],button,a,li,div,span,[role=\"button\"]'
                    );

                    const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();

                    for (const el of candidates) {{
                        if (!isVisible(el)) continue;
                        const txt = norm(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                        if (!txt) continue;
                        if (txt === target || txt.includes(target) || target.includes(txt)) {{
                            el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                            el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }}"""
            )
        )

    def _clip_content(self, content: str) -> str:
        if len(content) <= self._max_content_chars:
            return content
        return content[: self._max_content_chars - 32] + "\n...(truncated)"

    async def _dispatch_mouse_event(
        self,
        event_type: str,
        x: float,
        y: float,
        button: str = "none",
        click_count: int = 0,
    ) -> None:
        """Send a raw CDP mouse event to the currently focused tab."""
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

    # ------------------------------------------------------------------
    # Browser Protocol implementation
    # ------------------------------------------------------------------

    async def view_page(self) -> ToolResult:
        """Return the current page content and interactive elements."""
        try:
            session = await self._ensure_session()
            state = await session.get_browser_state_summary(include_screenshot=False)

            interactive_elements = await self._get_interactive_elements()

            content = ""
            if state.dom_state is not None:
                content = self._clip_content(state.dom_state.llm_representation())

            return ToolResult(
                success=True,
                data={
                    "interactive_elements": interactive_elements,
                    "content": content,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to view page: {exc}")

    async def navigate(self, url: str) -> ToolResult:
        """Navigate to the given URL."""
        try:
            session = await self._ensure_session()
            await session.navigate_to(url)
            await asyncio.sleep(0.5)
            interactive_elements = await self._get_interactive_elements()
            return ToolResult(
                success=True,
                data={"interactive_elements": interactive_elements},
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to navigate to {url}: {exc}")

    async def restart(self, url: str) -> ToolResult:
        """Restart the browser session and navigate to the given URL."""
        await self.cleanup()
        return await self.navigate(url)

    async def click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Click an element by DOM index or by screen coordinates."""
        try:
            if coordinate_x is not None and coordinate_y is not None:
                await self._dispatch_mouse_event(
                    "mousePressed", coordinate_x, coordinate_y, "left", 1
                )
                await self._dispatch_mouse_event(
                    "mouseReleased", coordinate_x, coordinate_y, "left", 1
                )
            elif index is not None:
                session = await self._ensure_session()
                last_error: Optional[str] = None
                for attempt in range(2):
                    node = await session.get_dom_element_by_index(index)
                    if node is None:
                        last_error = f"Cannot find interactive element with index {index}"
                        await asyncio.sleep(0.2)
                        continue

                    page = await self._get_current_page()
                    try:
                        element = await page.get_element(node.backend_node_id)
                        try:
                            await element.click()
                        except Exception:
                            await element.click(force=True)
                        last_error = None
                        break
                    except Exception as exc:
                        # Dynamic menu items frequently remount; fallback by text.
                        node_text = self._node_text(node)
                        if await self._click_by_text_fallback(node_text):
                            last_error = None
                            break
                        last_error = str(exc)
                        await asyncio.sleep(0.2)

                if last_error:
                    return ToolResult(success=False, message=f"Failed to click element: {last_error}")
            await asyncio.sleep(0.5)
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to click element: {exc}")

    async def hover(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Hover an element by DOM index or coordinates and return refreshed observability."""
        try:
            if coordinate_x is not None and coordinate_y is not None:
                await self._dispatch_mouse_event("mouseMoved", coordinate_x, coordinate_y)
            elif index is not None:
                session = await self._ensure_session()
                node = await session.get_dom_element_by_index(index)
                if node is None:
                    return ToolResult(
                        success=False,
                        message=f"Cannot find interactive element with index {index}",
                    )
                page = await self._get_current_page()
                element = await page.get_element(node.backend_node_id)
                await element.hover()
            else:
                return ToolResult(success=False, message="Either index or coordinate must be provided")

            await asyncio.sleep(0.4)
            return ToolResult(
                success=True,
                data={"interactive_elements": await self._get_interactive_elements()},
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to hover element: {exc}")

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Type text into an element identified by DOM index or screen coordinates."""
        try:
            page = await self._get_current_page()

            if coordinate_x is not None and coordinate_y is not None:
                # Click first to focus, then insert text via CDP
                await self._dispatch_mouse_event(
                    "mousePressed", coordinate_x, coordinate_y, "left", 1
                )
                await self._dispatch_mouse_event(
                    "mouseReleased", coordinate_x, coordinate_y, "left", 1
                )
                cdp_sess = await self._get_cdp_session()
                await cdp_sess.cdp_client.send.Input.insertText(
                    params={"text": text},
                    session_id=str(cdp_sess.session_id),
                )
            elif index is not None:
                session = await self._ensure_session()
                node = await session.get_dom_element_by_index(index)
                if node is None:
                    return ToolResult(
                        success=False,
                        message=f"Cannot find interactive element with index {index}",
                    )
                element = await page.get_element(node.backend_node_id)
                await element.fill(text)

            if press_enter:
                await page.press("Enter")

            await asyncio.sleep(0.5)
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to input text: {exc}")

    async def move_mouse(
        self,
        coordinate_x: float,
        coordinate_y: float,
    ) -> ToolResult:
        """Move the mouse cursor to the given coordinates."""
        try:
            await self._dispatch_mouse_event("mouseMoved", coordinate_x, coordinate_y)
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to move mouse: {exc}")

    async def press_key(self, key: str) -> ToolResult:
        """Simulate a key press."""
        try:
            page = await self._get_current_page()
            await page.press(key)
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to press key: {exc}")

    async def select_option(self, index: int, option: int) -> ToolResult:
        """Select an option in a <select> element by DOM index."""
        try:
            session = await self._ensure_session()
            node = await session.get_dom_element_by_index(index)
            if node is None:
                return ToolResult(
                    success=False,
                    message=f"Cannot find selector element with index {index}",
                )
            page = await self._get_current_page()
            element = await page.get_element(node.backend_node_id)
            await element.select_option(str(option))
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to select option: {exc}")

    async def scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        """Scroll the page upward (or to the very top when to_top is True)."""
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
        """Scroll the page downward (or to the very bottom when to_bottom is True)."""
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
        """Return a PNG screenshot of the current page."""
        session = await self._ensure_session()
        return await session.take_screenshot(full_page=bool(full_page))

    async def console_exec(self, javascript: str) -> ToolResult:
        """Execute arbitrary JavaScript in the current page context."""
        try:
            page = await self._get_current_page()
            # browser_use actor Page.evaluate() requires arrow-function syntax
            js = javascript.strip()
            if not (js.startswith("(") and "=>" in js):
                js = f"() => {{ {js} }}"
            result = await page.evaluate(js)
            return ToolResult(success=True, data={"result": result})
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to execute JavaScript: {exc}")

    async def console_view(self, max_lines: Optional[int] = None) -> ToolResult:
        """Return captured console log lines from the current page."""
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

    async def wait_for_selector(
        self,
        selector: str,
        text_contains: Optional[str] = None,
        timeout_ms: Optional[int] = 6000,
    ) -> ToolResult:
        """Wait for selector and optionally verify text in matched element."""
        try:
            page = await self._get_current_page()
            timeout = timeout_ms or 6000
            await page.wait_for_selector(selector, timeout=timeout, state="visible")

            if text_contains:
                ok = await page.evaluate(
                    """(sel, expected) => {
                        const el = document.querySelector(sel);
                        if (!el) return false;
                        const txt = (el.innerText || el.textContent || '').toLowerCase();
                        return txt.includes((expected || '').toLowerCase());
                    }""",
                    selector,
                    text_contains,
                )
                if not ok:
                    return ToolResult(
                        success=False,
                        message=f"Selector found but text not matched: {text_contains}",
                    )

            return ToolResult(
                success=True,
                data={
                    "selector": selector,
                    "text_contains": text_contains,
                    "interactive_elements": await self._get_interactive_elements(),
                },
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed waiting for selector: {exc}")

    async def accessibility_snapshot(
        self,
        max_nodes: Optional[int] = 200,
    ) -> ToolResult:
        """Return a lightweight accessibility-oriented snapshot via DOM/ARIA."""
        try:
            page = await self._get_current_page()
            limit = max(20, min(max_nodes or 200, 1000))
            tree = await page.evaluate(
                """(maxNodes) => {
                    const nodes = [];
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        if (nodes.length >= maxNodes) break;
                        const role = el.getAttribute('role');
                        const ariaLabel = el.getAttribute('aria-label');
                        const hasPopup = el.getAttribute('aria-haspopup');
                        const expanded = el.getAttribute('aria-expanded');
                        const tag = (el.tagName || '').toLowerCase();
                        const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                        if (!role && !ariaLabel && expanded === null && hasPopup === null) continue;
                        nodes.push({
                            role: role || tag,
                            name: ariaLabel || text?.slice(0, 80) || '',
                            expanded: expanded,
                            haspopup: hasPopup,
                            disabled: el.getAttribute('aria-disabled'),
                        });
                    }
                    return {
                        url: location.href || '',
                        title: document.title || '',
                        nodes
                    };
                }""",
                limit,
            )
            return ToolResult(success=True, data=tree)
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed accessibility snapshot: {exc}")
