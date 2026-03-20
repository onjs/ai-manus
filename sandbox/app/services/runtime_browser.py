import asyncio
import base64
import json
import time
from typing import Any

import httpx
import websockets


class _CDPSession:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._seq = 0

    async def __aenter__(self) -> "_CDPSession":
        self._ws = await websockets.connect(self._ws_url, max_size=8 * 1024 * 1024)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("CDP session is not connected")
        self._seq += 1
        req_id = self._seq
        await self._ws.send(
            json.dumps(
                {
                    "id": req_id,
                    "method": method,
                    "params": params or {},
                },
                ensure_ascii=False,
            )
        )

        while True:
            raw = await self._ws.recv()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                continue
            if int(payload.get("id", -1)) != req_id:
                continue
            if "error" in payload:
                raise RuntimeError(f"CDP {method} failed: {payload['error']}")
            result = payload.get("result")
            if isinstance(result, dict):
                return result
            return {}


class RuntimeBrowserService:
    def __init__(self, debugger_list_url: str = "http://127.0.0.1:9222/json/list"):
        self._debugger_list_url = debugger_list_url
        self._lock = asyncio.Lock()

    async def execute(self, function_name: str, function_args: dict[str, Any]) -> dict[str, Any]:
        fn = (function_name or "").strip()
        args = function_args or {}

        async with self._lock:
            try:
                if fn == "browser_view":
                    return await self._view()
                if fn == "browser_navigate":
                    return await self._navigate(str(args.get("url") or "").strip())
                if fn == "browser_restart":
                    return await self._restart(str(args.get("url") or "").strip())
                if fn == "browser_click":
                    return await self._click(
                        index=args.get("index"),
                        coordinate_x=args.get("coordinate_x"),
                        coordinate_y=args.get("coordinate_y"),
                    )
                if fn == "browser_hover_observe":
                    return await self._hover(
                        index=args.get("index"),
                        coordinate_x=args.get("coordinate_x"),
                        coordinate_y=args.get("coordinate_y"),
                    )
                if fn == "browser_input":
                    return await self._input(
                        text=str(args.get("text") or ""),
                        press_enter=bool(args.get("press_enter", False)),
                        index=args.get("index"),
                    )
                if fn == "browser_wait_for_selector":
                    return await self._wait_for_selector(
                        selector=str(args.get("selector") or ""),
                        text_contains=(str(args.get("text_contains")) if args.get("text_contains") is not None else None),
                        timeout_ms=int(args.get("timeout_ms") or 6000),
                    )
                if fn == "browser_accessibility_snapshot":
                    return await self._accessibility_snapshot(max_nodes=int(args.get("max_nodes") or 200))
                if fn == "browser_move_mouse":
                    return await self._move_mouse(
                        coordinate_x=args.get("coordinate_x"),
                        coordinate_y=args.get("coordinate_y"),
                    )
                if fn == "browser_press_key":
                    return await self._press_key(str(args.get("key") or ""))
                if fn == "browser_select_option":
                    return await self._select_option(index=args.get("index"), option=args.get("option"))
                if fn == "browser_scroll_down":
                    return await self._scroll(down=True, to_boundary=bool(args.get("to_bottom", False)))
                if fn == "browser_scroll_up":
                    return await self._scroll(down=False, to_boundary=bool(args.get("to_top", False)))
                if fn == "browser_console_exec":
                    return await self._console_exec(str(args.get("javascript") or ""))
                if fn == "browser_console_view":
                    return await self._console_view(max_lines=args.get("max_lines"))
                if fn == "browser_screenshot":
                    return await self._screenshot(full_page=bool(args.get("full_page", False)))
                if fn == "browser_screenshot_data_url":
                    return await self._screenshot_data_url(full_page=bool(args.get("full_page", False)))

                return {
                    "success": False,
                    "message": f"Unsupported browser function: {fn}",
                    "data": {},
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": str(e),
                    "data": {},
                }

    async def _pick_page_ws_url(self) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(self._debugger_list_url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("CDP target list is invalid")
        pages = [item for item in payload if isinstance(item, dict) and item.get("type") == "page"]
        if not pages:
            raise RuntimeError("No browser page target found")
        target = pages[-1]
        ws_url = target.get("webSocketDebuggerUrl")
        if not isinstance(ws_url, str) or not ws_url:
            raise RuntimeError("CDP target missing webSocketDebuggerUrl")
        return ws_url

    async def _open_session(self) -> _CDPSession:
        ws_url = await self._pick_page_ws_url()
        return _CDPSession(ws_url)

    @staticmethod
    def _unwrap_remote_value(result: dict[str, Any]) -> Any:
        rv = result.get("result")
        if not isinstance(rv, dict):
            return None
        if "value" in rv:
            return rv.get("value")
        return None

    async def _evaluate(self, cdp: _CDPSession, expression: str, await_promise: bool = True) -> Any:
        result = await cdp.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )
        return self._unwrap_remote_value(result)

    async def _capture_screenshot_bytes(self, cdp: _CDPSession, full_page: bool = False) -> bytes:
        if full_page:
            metrics = await cdp.call("Page.getLayoutMetrics")
            content_size = metrics.get("contentSize", {}) if isinstance(metrics, dict) else {}
            width = int(content_size.get("width", 0) or 0)
            height = int(content_size.get("height", 0) or 0)
            if width > 0 and height > 0:
                await cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "mobile": False,
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                    },
                )
        result = await cdp.call("Page.captureScreenshot", {"format": "png"})
        base64_data = result.get("data")
        if not isinstance(base64_data, str) or not base64_data:
            raise RuntimeError("captureScreenshot returned empty data")
        return base64.b64decode(base64_data)

    async def _capture_screenshot_data_url(self, cdp: _CDPSession, full_page: bool = False) -> str:
        if full_page:
            metrics = await cdp.call("Page.getLayoutMetrics")
            content_size = metrics.get("contentSize", {}) if isinstance(metrics, dict) else {}
            width = int(content_size.get("width", 0) or 0)
            height = int(content_size.get("height", 0) or 0)
            if width > 0 and height > 0:
                await cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "mobile": False,
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                    },
                )
        result = await cdp.call(
            "Page.captureScreenshot",
            {
                "format": "jpeg",
                "quality": 55,
            },
        )
        base64_data = result.get("data")
        if not isinstance(base64_data, str) or not base64_data:
            raise RuntimeError("captureScreenshot returned empty data")
        return f"data:image/jpeg;base64,{base64_data}"

    async def _collect_page_snapshot(self, cdp: _CDPSession) -> dict[str, Any]:
        snapshot = await self._evaluate(
            cdp,
            """(() => {
                const isVisible = (el) => {
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  if (rect.width <= 0 || rect.height <= 0) return false;
                  const style = window.getComputedStyle(el);
                  if (!style) return false;
                  return !(style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0');
                };
                const nodes = Array.from(document.querySelectorAll(
                  'button,a,input,textarea,select,[role="button"],[tabindex]:not([tabindex="-1"])'
                ));
                const interactive = [];
                let idx = 0;
                for (const node of nodes) {
                  if (!isVisible(node)) continue;
                  const txt = (node.innerText || node.textContent || node.getAttribute('aria-label') || node.getAttribute('placeholder') || '').trim().replace(/\s+/g, ' ');
                  node.setAttribute('data-manus-id', `manus-element-${idx}`);
                  interactive.push(`${idx}:<${(node.tagName || 'node').toLowerCase()}>${txt || '[No text]'}</${(node.tagName || 'node').toLowerCase()}>`);
                  idx += 1;
                  if (interactive.length >= 200) break;
                }
                const bodyText = (document.body?.innerText || '').trim();
                return {
                  content: bodyText.length > 12000 ? bodyText.slice(0, 12000) + '\n...(truncated)' : bodyText,
                  interactive_elements: interactive,
                };
            })()""",
        )
        if isinstance(snapshot, dict):
            return snapshot
        return {
            "content": "",
            "interactive_elements": [],
        }

    async def _view(self) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            data = await self._collect_page_snapshot(cdp)
            return {"success": True, "message": "ok", "data": data}

    async def _navigate(self, url: str) -> dict[str, Any]:
        if not url:
            return {"success": False, "message": "url is required", "data": {}}

        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            await cdp.call("Page.navigate", {"url": url})
            deadline = time.time() + 15
            while time.time() < deadline:
                state = await self._evaluate(cdp, "document.readyState")
                if state in {"interactive", "complete"}:
                    break
                await asyncio.sleep(0.25)
            data = await self._collect_page_snapshot(cdp)
            return {
                "success": True,
                "message": "ok",
                "data": {"interactive_elements": data.get("interactive_elements", [])},
            }

    async def _restart(self, url: str) -> dict[str, Any]:
        return await self._navigate(url)

    async def _click(self, index: Any = None, coordinate_x: Any = None, coordinate_y: Any = None) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")

            if coordinate_x is not None and coordinate_y is not None:
                x = float(coordinate_x)
                y = float(coordinate_y)
                await cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
                await cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
                await cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
            else:
                if index is None:
                    return {"success": False, "message": "index or coordinate is required", "data": {}}
                clicked = await self._evaluate(
                    cdp,
                    f"""(() => {{
                        const target = document.querySelector('[data-manus-id="manus-element-{int(index)}"]');
                        if (!target) return false;
                        target.scrollIntoView({{block: 'center'}});
                        target.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                        target.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, cancelable: true}}));
                        target.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true, cancelable: true}}));
                        target.click();
                        return true;
                    }})()""",
                )
                if not clicked:
                    return {"success": False, "message": f"interactive index not found: {index}", "data": {}}

            return {"success": True, "message": "ok", "data": None}

    async def _hover(self, index: Any = None, coordinate_x: Any = None, coordinate_y: Any = None) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            if coordinate_x is not None and coordinate_y is not None:
                await cdp.call(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": float(coordinate_x), "y": float(coordinate_y)},
                )
            else:
                if index is None:
                    return {"success": False, "message": "index or coordinate is required", "data": {}}
                hovered = await self._evaluate(
                    cdp,
                    f"""(() => {{
                        const target = document.querySelector('[data-manus-id="manus-element-{int(index)}"]');
                        if (!target) return false;
                        target.scrollIntoView({{block: 'center'}});
                        target.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                        target.dispatchEvent(new MouseEvent('mouseenter', {{bubbles: true}}));
                        return true;
                    }})()""",
                )
                if not hovered:
                    return {"success": False, "message": f"interactive index not found: {index}", "data": {}}
            await asyncio.sleep(0.25)
            data = await self._collect_page_snapshot(cdp)
            return {"success": True, "message": "ok", "data": data}

    async def _input(self, text: str, press_enter: bool, index: Any = None) -> dict[str, Any]:
        if index is None:
            return {"success": False, "message": "index is required for browser_input", "data": {}}
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            text_literal = json.dumps(text, ensure_ascii=False)
            set_result = await self._evaluate(
                cdp,
                f"""(() => {{
                    const target = document.querySelector('[data-manus-id="manus-element-{int(index)}"]');
                    if (!target) return false;
                    target.scrollIntoView({{block: 'center'}});
                    target.focus();
                    const value = {text_literal};
                    if ('value' in target) {{
                      target.value = value;
                    }} else {{
                      target.innerText = value;
                    }}
                    target.dispatchEvent(new Event('input', {{bubbles: true}}));
                    target.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }})()""",
            )
            if not set_result:
                return {"success": False, "message": f"interactive index not found: {index}", "data": {}}

            if press_enter:
                await cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter"})
                await cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter"})

            return {"success": True, "message": "ok", "data": None}

    async def _wait_for_selector(self, selector: str, text_contains: str | None, timeout_ms: int) -> dict[str, Any]:
        if not selector:
            return {"success": False, "message": "selector is required", "data": {}}
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            deadline = time.time() + (max(500, timeout_ms) / 1000)
            selector_literal = json.dumps(selector, ensure_ascii=False)
            text_literal = json.dumps(text_contains or "", ensure_ascii=False)
            while time.time() < deadline:
                matched = await self._evaluate(
                    cdp,
                    f"""(() => {{
                        const node = document.querySelector({selector_literal});
                        if (!node) return false;
                        const expected = {text_literal};
                        if (!expected) return true;
                        const text = (node.innerText || node.textContent || '').trim();
                        return text.includes(expected);
                    }})()""",
                )
                if matched:
                    return {"success": True, "message": "ok", "data": None}
                await asyncio.sleep(0.25)
            return {"success": False, "message": f"selector wait timeout: {selector}", "data": {}}

    async def _accessibility_snapshot(self, max_nodes: int) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            tree = await self._evaluate(
                cdp,
                f"""(() => {{
                    const rows = [];
                    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_ELEMENT);
                    let node = walker.currentNode;
                    while (node && rows.length < {max(10, max_nodes)}) {{
                        const role = node.getAttribute?.('role') || node.tagName?.toLowerCase?.() || 'node';
                        const name = node.getAttribute?.('aria-label') || node.innerText || node.textContent || '';
                        rows.push({{
                          role,
                          name: String(name).slice(0, 120).trim(),
                        }});
                        node = walker.nextNode();
                    }}
                    return rows;
                }})()""",
            )
            return {
                "success": True,
                "message": "ok",
                "data": {"nodes": tree if isinstance(tree, list) else []},
            }

    async def _move_mouse(self, coordinate_x: Any, coordinate_y: Any) -> dict[str, Any]:
        if coordinate_x is None or coordinate_y is None:
            return {"success": False, "message": "coordinate_x and coordinate_y are required", "data": {}}
        async with await self._open_session() as cdp:
            await cdp.call(
                "Input.dispatchMouseEvent",
                {"type": "mouseMoved", "x": float(coordinate_x), "y": float(coordinate_y)},
            )
            return {"success": True, "message": "ok", "data": None}

    async def _press_key(self, key: str) -> dict[str, Any]:
        if not key:
            return {"success": False, "message": "key is required", "data": {}}
        async with await self._open_session() as cdp:
            await cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": key})
            await cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key})
            return {"success": True, "message": "ok", "data": None}

    async def _select_option(self, index: Any, option: Any) -> dict[str, Any]:
        if index is None or option is None:
            return {"success": False, "message": "index and option are required", "data": {}}
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            selected = await self._evaluate(
                cdp,
                f"""(() => {{
                    const target = document.querySelector('[data-manus-id="manus-element-{int(index)}"]');
                    if (!target) return false;
                    if (!(target instanceof HTMLSelectElement)) return false;
                    target.selectedIndex = {int(option)};
                    target.dispatchEvent(new Event('input', {{bubbles: true}}));
                    target.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }})()""",
            )
            if not selected:
                return {"success": False, "message": f"selector element not found or invalid: {index}", "data": {}}
            return {"success": True, "message": "ok", "data": None}

    async def _scroll(self, down: bool, to_boundary: bool) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            if to_boundary:
                script = "window.scrollTo(0, document.body.scrollHeight);" if down else "window.scrollTo(0, 0);"
            else:
                script = "window.scrollBy(0, window.innerHeight);" if down else "window.scrollBy(0, -window.innerHeight);"
            await self._evaluate(cdp, script)
            return {"success": True, "message": "ok", "data": None}

    async def _console_exec(self, javascript: str) -> dict[str, Any]:
        if not javascript.strip():
            return {"success": False, "message": "javascript is required", "data": {}}
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            value = await self._evaluate(cdp, javascript, await_promise=True)
            return {"success": True, "message": "ok", "data": {"result": value}}

    async def _console_view(self, max_lines: Any) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            logs = await self._evaluate(cdp, "window.console.logs || []")
            if not isinstance(logs, list):
                logs = []
            if max_lines is not None:
                logs = logs[-max(0, int(max_lines)) :]
            return {"success": True, "message": "ok", "data": {"logs": logs}}

    async def _screenshot(self, full_page: bool) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            image = await self._capture_screenshot_bytes(cdp, full_page=full_page)
            return {"success": True, "message": "ok", "data": {"bytes": image}}

    async def _screenshot_data_url(self, full_page: bool) -> dict[str, Any]:
        async with await self._open_session() as cdp:
            await cdp.call("Page.enable")
            data_url = await self._capture_screenshot_data_url(cdp, full_page=full_page)
            return {"success": True, "message": "ok", "data": {"screenshot": data_url}}


runtime_browser_service = RuntimeBrowserService()
