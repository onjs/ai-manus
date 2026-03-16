from typing import Any, Dict, Optional, List, Tuple
import asyncio
import logging

from playwright.async_api import (
    async_playwright,
    Browser,
    Page,
    ElementHandle,
    TimeoutError as PlaywrightTimeoutError,
)

from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class PlaywrightBrowser:
    """Playwright client providing browser operations over CDP."""

    MAX_VIEW_CONTENT_CHARS = 12000
    MAX_CONTENT_LINES = 400
    MAX_INTERACTIVE_ELEMENTS = 160

    def __init__(self, cdp_url: str):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.cdp_url = cdp_url

    async def initialize(self) -> bool:
        """Initialize and ensure resources are available."""
        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_url)

                contexts = self.browser.contexts
                if contexts and len(contexts[0].pages) == 1:
                    page = contexts[0].pages[0]
                    page_url = await page.evaluate("window.location.href")
                    if (
                        page_url == "about:blank"
                        or page_url == "chrome://newtab/"
                        or page_url == "chrome://new-tab-page/"
                        or not page_url
                    ):
                        self.page = page
                    else:
                        self.page = await contexts[0].new_page()
                else:
                    context = contexts[0] if contexts else await self.browser.new_context()
                    self.page = await context.new_page()
                return True
            except Exception as exc:
                await self.cleanup()
                if attempt == max_retries - 1:
                    logger.error("Initialization failed (retried %d times): %s", max_retries, exc)
                    return False
                retry_delay = min(retry_delay * 2, 10)
                logger.warning("Initialization failed, will retry in %d seconds: %s", retry_delay, exc)
                await asyncio.sleep(retry_delay)
        return False

    async def cleanup(self) -> None:
        """Clean up Playwright resources."""
        try:
            if self.browser:
                for context in self.browser.contexts:
                    for page in context.pages:
                        if page != self.page or (self.page and not self.page.is_closed()):
                            await page.close()

            if self.page and not self.page.is_closed():
                await self.page.close()

            if self.browser:
                await self.browser.close()

            if self.playwright:
                await self.playwright.stop()
        except Exception as exc:
            logger.error("Error occurred when cleaning up resources: %s", exc)
        finally:
            self.page = None
            self.browser = None
            self.playwright = None

    async def _ensure_browser(self) -> None:
        if not self.browser or not self.page:
            if not await self.initialize():
                raise RuntimeError("Unable to initialize browser resources")

    async def _ensure_page(self) -> None:
        """Ensure the page exists and follows the latest active tab."""
        await self._ensure_browser()

        if not self.page:
            self.page = await self.browser.new_page()
            return

        contexts = self.browser.contexts
        if not contexts:
            return

        pages = contexts[0].pages
        if not pages:
            return

        rightmost_page = pages[-1]
        if self.page != rightmost_page:
            self.page = rightmost_page

    async def _get_dom_signature(self) -> Tuple[str, int, int]:
        await self._ensure_page()
        signature = await self.page.evaluate(
            """() => {
                const interactiveCount = document.querySelectorAll(
                  'button,a,input,textarea,select,[role="button"],[tabindex]:not([tabindex="-1"])'
                ).length;
                const textLength = (document.body?.innerText || '').length;
                return [document.readyState || 'unknown', interactiveCount, textLength];
            }"""
        )
        return (
            str(signature[0]) if isinstance(signature, list) and len(signature) > 0 else "unknown",
            int(signature[1]) if isinstance(signature, list) and len(signature) > 1 else 0,
            int(signature[2]) if isinstance(signature, list) and len(signature) > 2 else 0,
        )

    async def _wait_for_dom_stable(self, timeout: int = 5, stable_rounds: int = 3) -> bool:
        await self._ensure_page()

        start = asyncio.get_event_loop().time()
        interval = 0.25
        last_sig: Optional[Tuple[str, int, int]] = None
        stable_count = 0

        while asyncio.get_event_loop().time() - start < timeout:
            try:
                sig = await self._get_dom_signature()
            except Exception:
                await asyncio.sleep(interval)
                continue

            if sig == last_sig:
                stable_count += 1
            else:
                stable_count = 1
                last_sig = sig

            if stable_count >= stable_rounds and sig[0] in {"interactive", "complete"}:
                return True

            await asyncio.sleep(interval)

        return False

    async def wait_for_page_load(self, timeout: int = 15) -> bool:
        """Wait for DOM + network + short stabilization window."""
        await self._ensure_page()
        timeout_ms = max(1000, int(timeout * 1000))

        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            logger.debug("domcontentloaded wait timed out")

        try:
            await self.page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
        except PlaywrightTimeoutError:
            logger.debug("networkidle wait timed out")

        await self._wait_for_dom_stable(timeout=min(timeout, 5))
        return True

    async def _extract_content(self) -> str:
        """Extract clipped, structured text for LLM context."""
        await self._ensure_page()

        payload = await self.page.evaluate(
            """(maxLines) => {
                const isVisible = (element) => {
                    if (!element) return false;
                    const rect = element.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return false;
                    const style = window.getComputedStyle(element);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    return true;
                };

                const selectors = [
                    'h1','h2','h3','h4','p','li','td','th','label',
                    'button','a','input','textarea','select',
                    '[role="button"]','[aria-label]','[placeholder]','[data-testid]'
                ];

                const nodes = document.querySelectorAll(selectors.join(','));
                const lines = [];

                for (const node of nodes) {
                    if (lines.length >= maxLines) break;
                    if (!isVisible(node)) continue;

                    const tag = (node.tagName || 'node').toLowerCase();
                    let text = (node.innerText || '').trim().replace(/\\s+/g, ' ');

                    if (!text && (tag === 'input' || tag === 'textarea' || tag === 'select')) {
                        text = [
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('placeholder') || '',
                            node.value || '',
                            node.getAttribute('name') || '',
                            node.id || ''
                        ].filter(Boolean).join(' | ');
                    }

                    if (!text) continue;
                    if (text.length > 180) text = text.slice(0, 177) + '...';
                    lines.push(`${tag}: ${text}`);
                }

                return {
                    title: document.title || '',
                    url: location.href || '',
                    lines,
                };
            }""",
            self.MAX_CONTENT_LINES,
        )

        title = str(payload.get("title", "") if isinstance(payload, dict) else "")
        url = str(payload.get("url", "") if isinstance(payload, dict) else "")
        lines = payload.get("lines", []) if isinstance(payload, dict) else []

        if not isinstance(lines, list):
            lines = []

        text = "\n".join(str(line) for line in lines)
        assembled = f"title: {title}\nurl: {url}\n\n{text}".strip()

        if len(assembled) > self.MAX_VIEW_CONTENT_CHARS:
            assembled = assembled[: self.MAX_VIEW_CONTENT_CHARS - 32] + "\n...(truncated)"

        return assembled

    async def _extract_interactive_elements(self) -> List[str]:
        """Extract visible interactive elements and refresh index mapping."""
        await self._ensure_page()

        interactive_elements = await self.page.evaluate(
            """(maxElements) => {
                const isVisible = (element) => {
                    if (!element) return false;
                    const rect = element.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return false;
                    if (rect.bottom < 0 || rect.right < 0) return false;
                    const style = window.getComputedStyle(element);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    return true;
                };

                const elements = document.querySelectorAll(
                    'button, a, input, textarea, select, [role="button"], [tabindex]:not([tabindex="-1"])'
                );

                const result = [];
                let index = 0;

                for (const element of elements) {
                    if (result.length >= maxElements) break;
                    if (!isVisible(element)) continue;

                    const tag = (element.tagName || 'element').toLowerCase();
                    let text = (element.innerText || '').trim().replace(/\\s+/g, ' ');

                    if (!text) {
                        text = [
                            element.getAttribute('aria-label') || '',
                            element.getAttribute('placeholder') || '',
                            element.getAttribute('title') || '',
                            element.getAttribute('name') || '',
                            element.value || '',
                            element.id || ''
                        ].filter(Boolean).join(' | ');
                    }

                    if (!text) text = '[No text]';
                    if (text.length > 100) text = text.slice(0, 97) + '...';

                    element.setAttribute('data-manus-id', `manus-element-${index}`);

                    result.push({
                        index,
                        tag,
                        text,
                        selector: `[data-manus-id="manus-element-${index}"]`
                    });

                    index += 1;
                }

                return result;
            }""",
            self.MAX_INTERACTIVE_ELEMENTS,
        )

        self.page.interactive_elements_cache = interactive_elements

        formatted: List[str] = []
        for element in interactive_elements:
            formatted.append(f"{element['index']}:<{element['tag']}>{element['text']}</{element['tag']}>")

        return formatted

    async def _get_element_by_index(self, index: int, refresh_if_missing: bool = False) -> Optional[ElementHandle]:
        await self._ensure_page()

        if refresh_if_missing:
            await self._extract_interactive_elements()

        if (
            not hasattr(self.page, "interactive_elements_cache")
            or not self.page.interactive_elements_cache
            or index >= len(self.page.interactive_elements_cache)
        ):
            return None

        selector = f'[data-manus-id="manus-element-{index}"]'
        return await self.page.query_selector(selector)

    async def _scroll_into_view(self, element: ElementHandle) -> None:
        await self.page.evaluate(
            """(el) => {
                if (!el) return;
                el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
            }""",
            element,
        )

    async def _post_action_sync(self) -> None:
        await self.wait_for_page_load(timeout=8)
        try:
            await self._extract_interactive_elements()
        except Exception as exc:
            logger.debug("Failed to refresh interactive cache after action: %s", exc)

    async def view_page(self) -> ToolResult:
        await self._ensure_page()
        await self.wait_for_page_load(timeout=15)
        interactive_elements = await self._extract_interactive_elements()

        return ToolResult(
            success=True,
            data={
                "interactive_elements": interactive_elements,
                "content": await self._extract_content(),
            },
        )

    async def navigate(self, url: str, timeout: Optional[int] = 15000) -> ToolResult:
        await self._ensure_page()
        try:
            self.page.interactive_elements_cache = []
            await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            await self._post_action_sync()
            return ToolResult(
                success=True,
                data={"interactive_elements": await self._extract_interactive_elements()},
            )
        except Exception as exc:
            logger.warning("Failed to navigate to %s: %s", url, exc)
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
        await self._ensure_page()

        if coordinate_x is not None and coordinate_y is not None:
            try:
                await self.page.mouse.click(coordinate_x, coordinate_y)
                await self._post_action_sync()
                return ToolResult(success=True)
            except Exception as exc:
                return ToolResult(success=False, message=f"Failed to click at coordinate: {exc}")

        if index is None:
            return ToolResult(success=False, message="Either index or coordinate must be provided")

        last_error: Optional[str] = None
        for attempt in range(2):
            try:
                element = await self._get_element_by_index(index, refresh_if_missing=(attempt > 0))
                if not element:
                    last_error = f"Cannot find interactive element with index {index}"
                    continue
                await self._scroll_into_view(element)
                await element.click(timeout=5000)
                await self._post_action_sync()
                return ToolResult(success=True)
            except Exception as exc:
                last_error = str(exc)

        return ToolResult(success=False, message=f"Failed to click element: {last_error}")

    async def hover(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        """Hover element or coordinates, then re-observe dynamic DOM changes."""
        await self._ensure_page()

        if coordinate_x is not None and coordinate_y is not None:
            try:
                await self.page.mouse.move(coordinate_x, coordinate_y)
                await asyncio.sleep(0.3)
                await self._post_action_sync()
                return ToolResult(
                    success=True,
                    data={"interactive_elements": await self._extract_interactive_elements()},
                )
            except Exception as exc:
                return ToolResult(success=False, message=f"Failed to hover at coordinate: {exc}")

        if index is None:
            return ToolResult(success=False, message="Either index or coordinate must be provided")

        last_error: Optional[str] = None
        for attempt in range(2):
            try:
                element = await self._get_element_by_index(index, refresh_if_missing=(attempt > 0))
                if not element:
                    last_error = f"Cannot find interactive element with index {index}"
                    continue
                await self._scroll_into_view(element)
                await element.hover(timeout=5000)
                await asyncio.sleep(0.3)
                await self._post_action_sync()
                return ToolResult(
                    success=True,
                    data={"interactive_elements": await self._extract_interactive_elements()},
                )
            except Exception as exc:
                last_error = str(exc)
        return ToolResult(success=False, message=f"Failed to hover element: {last_error}")

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        await self._ensure_page()

        if coordinate_x is not None and coordinate_y is not None:
            try:
                await self.page.mouse.click(coordinate_x, coordinate_y)
                await self.page.keyboard.type(text)
                if press_enter:
                    await self.page.keyboard.press("Enter")
                await self._post_action_sync()
                return ToolResult(success=True)
            except Exception as exc:
                return ToolResult(success=False, message=f"Failed to input at coordinate: {exc}")

        if index is None:
            return ToolResult(success=False, message="Either index or coordinate must be provided")

        last_error: Optional[str] = None
        for attempt in range(2):
            try:
                element = await self._get_element_by_index(index, refresh_if_missing=(attempt > 0))
                if not element:
                    last_error = f"Cannot find interactive element with index {index}"
                    continue

                await self._scroll_into_view(element)

                try:
                    await element.fill("")
                    await element.type(text)
                except Exception:
                    await element.click()
                    await self.page.keyboard.type(text)

                if press_enter:
                    await self.page.keyboard.press("Enter")

                await self._post_action_sync()
                return ToolResult(success=True)
            except Exception as exc:
                last_error = str(exc)

        return ToolResult(success=False, message=f"Failed to input text: {last_error}")

    async def move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        await self._ensure_page()
        await self.page.mouse.move(coordinate_x, coordinate_y)
        return ToolResult(success=True)

    async def press_key(self, key: str) -> ToolResult:
        await self._ensure_page()
        await self.page.keyboard.press(key)
        await self._post_action_sync()
        return ToolResult(success=True)

    async def select_option(self, index: int, option: int) -> ToolResult:
        await self._ensure_page()

        last_error: Optional[str] = None
        for attempt in range(2):
            try:
                element = await self._get_element_by_index(index, refresh_if_missing=(attempt > 0))
                if not element:
                    last_error = f"Cannot find selector element with index {index}"
                    continue

                await self._scroll_into_view(element)
                await element.select_option(index=option)
                await self._post_action_sync()
                return ToolResult(success=True)
            except Exception as exc:
                last_error = str(exc)

        return ToolResult(success=False, message=f"Failed to select option: {last_error}")

    async def scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        await self._ensure_page()
        if to_top:
            await self.page.evaluate("window.scrollTo(0, 0)")
        else:
            await self.page.evaluate("window.scrollBy(0, -window.innerHeight)")
        await self._extract_interactive_elements()
        return ToolResult(success=True)

    async def scroll_down(self, to_bottom: Optional[bool] = None) -> ToolResult:
        await self._ensure_page()
        if to_bottom:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        else:
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
        await self._extract_interactive_elements()
        return ToolResult(success=True)

    async def screenshot(self, full_page: Optional[bool] = False) -> bytes:
        await self._ensure_page()
        return await self.page.screenshot(full_page=full_page, type="png")

    async def console_exec(self, javascript: str) -> ToolResult:
        await self._ensure_page()
        try:
            result = await self.page.evaluate(javascript)
            return ToolResult(success=True, data={"result": result})
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed to execute JavaScript: {exc}")

    async def console_view(self, max_lines: Optional[int] = None) -> ToolResult:
        await self._ensure_page()
        logs = await self.page.evaluate(
            """() => {
                return window.console.logs || [];
            }"""
        )
        if max_lines is not None and isinstance(logs, list):
            logs = logs[-max_lines:]
        return ToolResult(success=True, data={"logs": logs})

    async def wait_for_selector(
        self,
        selector: str,
        text_contains: Optional[str] = None,
        timeout_ms: Optional[int] = 6000,
    ) -> ToolResult:
        await self._ensure_page()
        timeout = timeout_ms or 6000
        try:
            handle = await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            if handle is None:
                return ToolResult(success=False, message=f"Selector not found: {selector}")

            if text_contains:
                matched = await self.page.evaluate(
                    """(el, expected) => {
                        const txt = (el?.innerText || el?.textContent || '').toLowerCase();
                        return txt.includes((expected || '').toLowerCase());
                    }""",
                    handle,
                    text_contains,
                )
                if not matched:
                    return ToolResult(
                        success=False,
                        message=f"Selector found but text not matched: {text_contains}",
                    )

            await self._post_action_sync()
            return ToolResult(
                success=True,
                data={
                    "selector": selector,
                    "text_contains": text_contains,
                    "interactive_elements": await self._extract_interactive_elements(),
                },
            )
        except PlaywrightTimeoutError:
            return ToolResult(success=False, message=f"Timeout waiting for selector: {selector}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed waiting for selector: {exc}")

    @staticmethod
    def _prune_a11y_tree(node: Any, max_nodes: int, counter: List[int]) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None
        if counter[0] >= max_nodes:
            return None
        counter[0] += 1

        keep_keys = {
            "role",
            "name",
            "value",
            "description",
            "focused",
            "disabled",
            "checked",
            "expanded",
            "selected",
            "level",
            "haspopup",
        }
        trimmed: Dict[str, Any] = {}
        for key in keep_keys:
            if key in node and node[key] not in (None, "", False):
                trimmed[key] = node[key]

        children = node.get("children")
        if isinstance(children, list):
            kept_children: List[Dict[str, Any]] = []
            for child in children:
                pruned = PlaywrightBrowser._prune_a11y_tree(child, max_nodes, counter)
                if pruned:
                    kept_children.append(pruned)
            if kept_children:
                trimmed["children"] = kept_children

        return trimmed if trimmed else None

    async def accessibility_snapshot(
        self,
        max_nodes: Optional[int] = 200,
    ) -> ToolResult:
        await self._ensure_page()
        try:
            tree = await self.page.accessibility.snapshot(interesting_only=True)
            if tree is None:
                return ToolResult(success=True, data={"tree": None})

            limit = max(20, min(max_nodes or 200, 1000))
            counter = [0]
            pruned = self._prune_a11y_tree(tree, limit, counter)
            return ToolResult(
                success=True,
                data={
                    "tree": pruned,
                    "node_count": counter[0],
                    "url": self.page.url,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Failed accessibility snapshot: {exc}")
