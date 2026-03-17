import json
import logging
import re
import time
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.utils.json import parse_json_markdown, parse_partial_json
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.domain.external.browser import Browser
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class BrowserEngineAction(BaseModel):
    action: Literal[
        "navigate",
        "click",
        "hover_click",
        "input",
        "set_date_field",
        "set_select_field",
        "set_people_field",
        "press_key",
        "scroll_down",
        "scroll_up",
        "wait_for_selector",
        "finish",
        "ask_user",
    ]
    reason: str = ""
    url: Optional[str] = None
    index: Optional[int] = None
    text: Optional[str] = None
    input_text: Optional[str] = None
    press_enter: bool = False
    key: Optional[str] = None
    selector: Optional[str] = None
    text_contains: Optional[str] = None
    field_label: Optional[str] = None
    field_value: Optional[str] = None
    date_expr: Optional[str] = None
    success_criteria: Optional[str] = None
    confidence: float = 0.5


class BrowserEngineTrace(BaseModel):
    round: int
    action: str
    reason: str = ""
    status: Literal["ok", "recovered", "failed", "finish", "ask_user"] = "ok"
    detail: str = ""
    verify: Optional[bool] = None


class BrowserEngine:
    """Unified browser decision layer for multi-step web operations."""

    _SYSTEM = (
        "You are BrowserEnginePlanner. "
        "Choose exactly one next browser action in strict JSON. "
        "Prefer deterministic actions and always think about verification. "
        "For dynamic menus or dropdowns, choose hover_click before click. "
        "For form filling, split into small steps and verify after each critical action. "
        "Prefer dedicated actions set_date_field/set_select_field/set_people_field for complex enterprise forms. "
        "If goal is complete, return action=finish. "
        "If user intervention is required (captcha/login/2fa), return action=ask_user."
    )

    _ACTION_SCHEMA = {
        "action": "navigate|click|hover_click|input|set_date_field|set_select_field|set_people_field|press_key|scroll_down|scroll_up|wait_for_selector|finish|ask_user",
        "reason": "why this action",
        "url": "required for navigate",
        "index": "interactive element index if needed",
        "text": "target text hint (menu item / button / field label)",
        "input_text": "required for input",
        "field_label": "required for set_date_field/set_select_field/set_people_field",
        "field_value": "required for set_select_field/set_people_field",
        "date_expr": "required for set_date_field, supports today/tomorrow/next_week/next_monday/YYYY-MM-DD",
        "press_enter": "bool for input",
        "key": "required for press_key",
        "selector": "verification or wait target",
        "text_contains": "optional text check",
        "success_criteria": "what should change after this action",
        "confidence": "0~1",
    }

    def __init__(self, browser: Browser):
        self._browser = browser
        settings = get_settings()
        self._vision_enabled = bool(settings.browser_engine_vision_enabled)
        self._vision_runtime_enabled = self._vision_enabled
        self._vision_max_image_bytes = max(100_000, int(settings.browser_engine_vision_max_image_bytes or 350_000))
        self._vision_round_limit = max(1, min(int(settings.browser_engine_vision_round_limit or 6), 50))
        kwargs = dict(
            model=settings.model_name,
            model_provider=settings.model_provider,
            temperature=min(settings.temperature, 0.4),
            max_tokens=min(settings.max_tokens, 1200),
            base_url=settings.api_base,
        )
        if settings.extra_headers:
            kwargs["default_headers"] = settings.extra_headers
        self._model = init_chat_model(**kwargs)

    @staticmethod
    def _coerce_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text is not None:
                        parts.append(str(text))
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _extract_url(content: str) -> str:
        if not content:
            return ""
        for line in content.splitlines():
            if line.lower().startswith("url:"):
                return line.split(":", 1)[1].strip()
        m = re.search(r"https?://[^\s]+", content)
        return m.group(0) if m else ""

    @staticmethod
    def _safe_json_parse(text: str) -> Optional[Dict[str, Any]]:
        raw = (text or "").strip()
        if not raw:
            return None
        candidates: List[str] = [raw]
        if "{" in raw and "}" in raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                candidates.append(raw[start : end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            try:
                parsed = parse_json_markdown(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            try:
                parsed = parse_partial_json(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    @staticmethod
    def _clip_lines(lines: List[str], max_items: int = 80) -> List[str]:
        if len(lines) <= max_items:
            return lines
        return lines[:max_items] + [f"... ({len(lines) - max_items} more elements)"]

    @staticmethod
    def _perception_fingerprint(perception: Dict[str, Any]) -> str:
        """A lightweight fingerprint for progress detection."""
        url = str(perception.get("url", "") or "")
        content = str(perception.get("content", "") or "")
        elems = perception.get("interactive_elements", [])
        if not isinstance(elems, list):
            elems = []
        elems_sig = "|".join(str(x) for x in elems[:25])
        # Keep this deterministic and cheap; no cryptographic needs here.
        return f"{url}##{content[:1200]}##{elems_sig}"

    @staticmethod
    def _extract_quoted_value(goal: str, key: str) -> str:
        if not goal:
            return ""
        patterns = [
            rf"{re.escape(key)}\\s*[\"“']([^\"”']+)[\"”']",
            rf"{re.escape(key)}[:：]\\s*[\"“']([^\"”']+)[\"”']",
        ]
        for pattern in patterns:
            matched = re.search(pattern, goal)
            if matched:
                return matched.group(1).strip()
        return ""

    @staticmethod
    def _normalize_date_expr(date_expr: str) -> Optional[str]:
        raw = (date_expr or "").strip()
        if not raw:
            return datetime.now().strftime("%Y-%m-%d")
        lowered = raw.lower()
        now = datetime.now()
        if lowered in {"today", "今天"}:
            return now.strftime("%Y-%m-%d")
        if lowered in {"tomorrow", "明天"}:
            return (now + timedelta(days=1)).strftime("%Y-%m-%d")
        if lowered in {"next_week", "下周"}:
            return (now + timedelta(days=7)).strftime("%Y-%m-%d")
        if lowered in {"next_monday", "下周一"}:
            days = (7 - now.weekday()) % 7
            days = 7 if days == 0 else days
            return (now + timedelta(days=days)).strftime("%Y-%m-%d")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            return raw
        return None

    @staticmethod
    def _extract_console_result_data(result: ToolResult) -> Dict[str, Any]:
        if not result.success:
            return {}
        payload = result.data if isinstance(result.data, dict) else {}
        value = payload.get("result", payload)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"value": value}
        if isinstance(value, dict):
            return value
        return {"value": value}

    async def _invoke_planner(self, prompt: str, screenshot_data_url: Optional[str] = None):
        text_message = HumanMessage(content=prompt)
        if screenshot_data_url and self._vision_runtime_enabled:
            try:
                multimodal_message = HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": screenshot_data_url}},
                    ]
                )
                return await self._model.ainvoke([SystemMessage(content=self._SYSTEM), multimodal_message])
            except Exception as exc:
                self._vision_runtime_enabled = False
                logger.warning("BrowserEngine vision call failed, fallback to text-only planner: %s", exc)
        return await self._model.ainvoke([SystemMessage(content=self._SYSTEM), text_message])

    async def _capture_screenshot_data_url(self) -> Optional[str]:
        if not self._vision_runtime_enabled:
            return None
        try:
            screenshot = await self._browser.screenshot(full_page=False)
            if not screenshot:
                return None
            if len(screenshot) > self._vision_max_image_bytes:
                logger.info(
                    "BrowserEngine skip vision image: screenshot too large (%s bytes > %s)",
                    len(screenshot),
                    self._vision_max_image_bytes,
                )
                return None
            encoded = base64.b64encode(screenshot).decode("ascii")
            return f"data:image/png;base64,{encoded}"
        except Exception as exc:
            logger.debug("BrowserEngine capture screenshot failed, skip vision this round: %s", exc)
            return None

    async def set_date_field(self, field_label: str, date_expr: str) -> ToolResult:
        normalized = self._normalize_date_expr(date_expr)
        if not normalized:
            return ToolResult(success=False, message=f"unsupported date_expr: {date_expr}")

        label_literal = json.dumps((field_label or "").strip(), ensure_ascii=False)
        value_literal = json.dumps(normalized, ensure_ascii=False)
        script = f"""() => {{
            const labelText = {label_literal};
            const targetDate = {value_literal};
            const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();
            const contains = (a, b) => a && b && (a.includes(b) || b.includes(a));
            const isVisible = (el) => {{
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(el);
                if (!style) return false;
                return !(style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0');
            }};
            const textOf = (el) => norm(el?.innerText || el?.textContent || el?.getAttribute('aria-label') || el?.getAttribute('placeholder') || el?.getAttribute('name') || '');
            const labelNorm = norm(labelText);
            const controls = Array.from(document.querySelectorAll('input,textarea,[contenteditable=\"true\"],[role=\"textbox\"],[role=\"combobox\"]')).filter(isVisible);
            let best = null;
            let bestScore = -1;
            const scoreControl = (el) => {{
                let score = 0;
                const tag = (el.tagName || '').toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                const own = textOf(el);
                if (labelNorm && contains(own, labelNorm)) score += 8;
                if (labelNorm && ['aria-label','placeholder','name','id'].some(k => contains(norm(el.getAttribute(k) || ''), labelNorm))) score += 12;
                if (type === 'date' || type === 'datetime-local' || type === 'month' || type === 'week') score += 18;
                if (/(date|time|calendar|日期|时间)/.test(type + ' ' + own)) score += 10;
                const parent = el.closest('label,form,fieldset,section,div');
                if (parent && labelNorm && contains(textOf(parent), labelNorm)) score += 10;
                if (tag === 'input') score += 4;
                return score;
            }};
            for (const control of controls) {{
                const score = scoreControl(control);
                if (score > bestScore) {{
                    best = control;
                    bestScore = score;
                }}
            }}
            if (!best) {{
                return {{ ok: false, reason: 'no_target_control' }};
            }}
            const tag = (best.tagName || '').toLowerCase();
            const type = (best.getAttribute('type') || '').toLowerCase();
            best.focus();
            if (tag === 'input' || tag === 'textarea') {{
                best.value = targetDate;
            }} else if (best.getAttribute('contenteditable') === 'true') {{
                best.innerText = targetDate;
            }} else {{
                best.value = targetDate;
            }}
            best.dispatchEvent(new Event('input', {{ bubbles: true }}));
            best.dispatchEvent(new Event('change', {{ bubbles: true }}));
            best.dispatchEvent(new Event('blur', {{ bubbles: true }}));
            const currentValue = (best.value || best.innerText || '').trim();
            return {{
                ok: !!currentValue,
                value: currentValue,
                matched_label: labelText,
                tag,
                type
            }};
        }}"""
        result = await self._browser.console_exec(script)
        data = self._extract_console_result_data(result)
        ok = bool(result.success and data.get("ok"))
        return ToolResult(
            success=ok,
            message=None if ok else (result.message or "set_date_field failed"),
            data=data or None,
        )

    async def set_select_field(self, field_label: str, field_value: str) -> ToolResult:
        label_literal = json.dumps((field_label or "").strip(), ensure_ascii=False)
        value_literal = json.dumps((field_value or "").strip(), ensure_ascii=False)
        script = f"""() => {{
            const labelText = {label_literal};
            const expected = {value_literal};
            const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();
            const contains = (a, b) => a && b && (a.includes(b) || b.includes(a));
            const isVisible = (el) => {{
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(el);
                if (!style) return false;
                return !(style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0');
            }};
            const textOf = (el) => norm(el?.innerText || el?.textContent || el?.getAttribute('aria-label') || el?.getAttribute('placeholder') || el?.getAttribute('name') || '');
            const clickEl = (el) => {{
                el.dispatchEvent(new MouseEvent('mouseover', {{ bubbles: true }}));
                el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
                el.click();
            }};
            const labelNorm = norm(labelText);
            const expectedNorm = norm(expected);
            const controls = Array.from(document.querySelectorAll('select,[role=\"combobox\"],input,button,div')).filter(isVisible);
            let target = null;
            let bestScore = -1;
            for (const el of controls) {{
                let score = 0;
                const own = textOf(el);
                const role = norm(el.getAttribute('role') || '');
                const tag = (el.tagName || '').toLowerCase();
                if (labelNorm && contains(own, labelNorm)) score += 10;
                if (labelNorm && ['aria-label','placeholder','name','id'].some(k => contains(norm(el.getAttribute(k) || ''), labelNorm))) score += 12;
                if (tag === 'select') score += 20;
                if (role === 'combobox') score += 16;
                const parent = el.closest('label,form,fieldset,section,div');
                if (parent && labelNorm && contains(textOf(parent), labelNorm)) score += 8;
                if (score > bestScore) {{
                    bestScore = score;
                    target = el;
                }}
            }}
            if (!target) return {{ ok: false, reason: 'no_target_control' }};

            if ((target.tagName || '').toLowerCase() === 'select') {{
                const options = Array.from(target.options || []);
                let chosen = null;
                for (const opt of options) {{
                    const txt = norm(opt.text || opt.label || '');
                    const val = norm(opt.value || '');
                    if (txt === expectedNorm || val === expectedNorm || txt.includes(expectedNorm) || expectedNorm.includes(txt)) {{
                        chosen = opt;
                        break;
                    }}
                }}
                if (!chosen) return {{ ok: false, reason: 'option_not_found_native' }};
                target.value = chosen.value;
                target.dispatchEvent(new Event('input', {{ bubbles: true }}));
                target.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ ok: true, selected: chosen.text || chosen.value, mode: 'native_select' }};
            }}

            clickEl(target);
            const optionNodes = Array.from(document.querySelectorAll(
                '[role=\"option\"],[role=\"menuitem\"],li,button,div,span'
            )).filter(isVisible);
            let chosenEl = null;
            for (const el of optionNodes) {{
                const txt = textOf(el);
                if (!txt) continue;
                if (txt === expectedNorm || txt.includes(expectedNorm) || expectedNorm.includes(txt)) {{
                    chosenEl = el;
                    break;
                }}
            }}
            if (!chosenEl) {{
                if (target.tagName && target.tagName.toLowerCase() === 'input') {{
                    target.value = expected;
                    target.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    target.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
                    target.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', bubbles: true }}));
                    return {{ ok: true, selected: expected, mode: 'input_fallback' }};
                }}
                return {{ ok: false, reason: 'option_not_found_overlay' }};
            }}
            clickEl(chosenEl);
            return {{ ok: true, selected: chosenEl.innerText || chosenEl.textContent || expected, mode: 'overlay_option' }};
        }}"""
        result = await self._browser.console_exec(script)
        data = self._extract_console_result_data(result)
        ok = bool(result.success and data.get("ok"))
        return ToolResult(
            success=ok,
            message=None if ok else (result.message or "set_select_field failed"),
            data=data or None,
        )

    async def set_people_field(self, field_label: str, field_value: str) -> ToolResult:
        label_literal = json.dumps((field_label or "").strip(), ensure_ascii=False)
        value_literal = json.dumps((field_value or "").strip(), ensure_ascii=False)
        script = f"""() => {{
            const labelText = {label_literal};
            const expected = {value_literal};
            const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();
            const contains = (a, b) => a && b && (a.includes(b) || b.includes(a));
            const isVisible = (el) => {{
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(el);
                if (!style) return false;
                return !(style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0');
            }};
            const textOf = (el) => norm(el?.innerText || el?.textContent || el?.getAttribute('aria-label') || el?.getAttribute('placeholder') || el?.getAttribute('name') || '');
            const labelNorm = norm(labelText);
            const controls = Array.from(document.querySelectorAll('input,textarea,[contenteditable=\"true\"],[role=\"textbox\"],[role=\"combobox\"]')).filter(isVisible);
            let target = null;
            let bestScore = -1;
            for (const el of controls) {{
                let score = 0;
                const own = textOf(el);
                if (labelNorm && contains(own, labelNorm)) score += 10;
                if (labelNorm && ['aria-label','placeholder','name','id'].some(k => contains(norm(el.getAttribute(k) || ''), labelNorm))) score += 12;
                const parent = el.closest('label,form,fieldset,section,div');
                if (parent && labelNorm && contains(textOf(parent), labelNorm)) score += 8;
                if (/(user|owner|assignee|member|审批|负责人|处理人|人员)/.test(own)) score += 6;
                if (score > bestScore) {{
                    bestScore = score;
                    target = el;
                }}
            }}
            if (!target) return {{ ok: false, reason: 'no_target_control' }};
            target.focus();
            if ((target.tagName || '').toLowerCase() === 'input' || (target.tagName || '').toLowerCase() === 'textarea') {{
                target.value = expected;
            }} else if (target.getAttribute('contenteditable') === 'true') {{
                target.innerText = expected;
            }} else {{
                target.value = expected;
            }}
            target.dispatchEvent(new Event('input', {{ bubbles: true }}));
            target.dispatchEvent(new Event('change', {{ bubbles: true }}));
            target.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
            target.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', bubbles: true }}));
            const current = (target.value || target.innerText || '').trim();
            return {{ ok: !!current, value: current }};
        }}"""
        result = await self._browser.console_exec(script)
        data = self._extract_console_result_data(result)
        ok = bool(result.success and data.get("ok"))
        return ToolResult(
            success=ok,
            message=None if ok else (result.message or "set_people_field failed"),
            data=data or None,
        )

    async def _perceive(self, include_screenshot: bool = False) -> Dict[str, Any]:
        view = await self._browser.view_page()
        a11y = await self._browser.accessibility_snapshot(max_nodes=160)

        view_data = view.data if isinstance(view.data, dict) else {}
        interactive_elements = view_data.get("interactive_elements", [])
        if not isinstance(interactive_elements, list):
            interactive_elements = []

        content = self._coerce_text(view_data.get("content"))
        url = self._extract_url(content)
        a11y_data = a11y.data if isinstance(a11y.data, dict) else {}
        screenshot_data_url = None
        if include_screenshot:
            screenshot_data_url = await self._capture_screenshot_data_url()

        return {
            "ok": bool(view.success),
            "interactive_elements": self._clip_lines([str(x) for x in interactive_elements], 90),
            "content": content[:12000],
            "url": url,
            "a11y": a11y_data if a11y.success else {},
            "screenshot_data_url": screenshot_data_url,
            "view_error": view.message or "",
        }

    async def _plan_action(
        self,
        goal: str,
        expected_result: str,
        extra_context: str,
        round_idx: int,
        history: List[BrowserEngineTrace],
        perception: Dict[str, Any],
    ) -> BrowserEngineAction:
        compact_history = [
            {
                "round": item.round,
                "action": item.action,
                "status": item.status,
                "detail": item.detail[:240],
            }
            for item in history[-8:]
        ]
        prompt = (
            f"Goal:\n{goal}\n\n"
            f"Expected Result:\n{expected_result or '(not specified)'}\n\n"
            f"Extra Context:\n{extra_context or '(none)'}\n\n"
            f"Round: {round_idx}\n\n"
            f"Current URL: {perception.get('url', '')}\n\n"
            f"Interactive Elements:\n"
            + "\n".join(perception.get("interactive_elements", []))
            + "\n\n"
            + f"Page Content Excerpt:\n{perception.get('content', '')[:3500]}\n\n"
            + f"A11y Snapshot:\n{json.dumps(perception.get('a11y', {}), ensure_ascii=False)[:2500]}\n\n"
            + f"Recent Trace:\n{json.dumps(compact_history, ensure_ascii=False)}\n\n"
            + f"Return JSON using this schema:\n{json.dumps(self._ACTION_SCHEMA, ensure_ascii=False)}\n\n"
            + "Hard rules:\n"
            + "- Only one action.\n"
            + "- If action is click/hover_click/input, provide index whenever possible.\n"
            + "- For date/time fields, use set_date_field with field_label + date_expr.\n"
            + "- For dropdown fields, use set_select_field with field_label + field_value.\n"
            + "- For people/assignee fields, use set_people_field with field_label + field_value.\n"
            + "- Prefer hover_click on dynamic menus/dropdowns.\n"
            + "- Do not repeat the same click path many times; change strategy when no progress.\n"
            + "- For menu/dropdown tasks, prefer selecting visible trigger first, then pick target option text.\n"
            + "- If goal already completed, return finish.\n"
            + "- If login/captcha/2fa blocks automation, return ask_user.\n"
        )

        response = await self._invoke_planner(
            prompt=prompt,
            screenshot_data_url=perception.get("screenshot_data_url"),
        )
        content = self._coerce_text(getattr(response, "content", ""))
        parsed = self._safe_json_parse(content)
        if parsed is None:
            logger.warning("BrowserEngine planner JSON parse failed, fallback to scroll_down")
            return BrowserEngineAction(action="scroll_down", reason="fallback_after_parse_failure")
        try:
            return BrowserEngineAction.model_validate(parsed)
        except Exception as exc:
            logger.warning("BrowserEngine planner schema invalid (%s), fallback scroll_down", exc)
            return BrowserEngineAction(action="scroll_down", reason="fallback_after_schema_failure")

    async def _click_by_text_fallback(self, text: str) -> ToolResult:
        safe = (text or "").strip()
        if not safe:
            return ToolResult(success=False, message="empty fallback text")
        escaped = safe.replace("\\", "\\\\").replace("'", "\\'")
        script = f"""() => {{
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
            const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();
            const candidates = document.querySelectorAll(
                '[role="menuitem"],[role="option"],button,a,li,div,span,[role="button"],label,input'
            );
            for (const el of candidates) {{
                if (!isVisible(el)) continue;
                const txt = norm(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '');
                if (!txt) continue;
                if (txt === target || txt.includes(target) || target.includes(txt)) {{
                    el.dispatchEvent(new MouseEvent('mouseover', {{ bubbles: true }}));
                    el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                    el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
                    el.click();
                    return true;
                }}
            }}
            return false;
        }}"""
        js_result = await self._browser.console_exec(script)
        ok = bool(
            js_result.success
            and isinstance(js_result.data, dict)
            and bool(js_result.data.get("result"))
        )
        return ToolResult(success=ok, message=None if ok else "text fallback click failed")

    @staticmethod
    def _extract_quoted_candidates(goal: str) -> List[str]:
        if not goal:
            return []
        raw = re.findall(r"[\"“']([^\"”']+)[\"”']", goal)
        candidates: List[str] = []
        for item in raw:
            text = (item or "").strip()
            if not text:
                continue
            if text not in candidates:
                candidates.append(text)
        return candidates

    async def _shortcut_click_menu_and_option(
        self,
        trigger_hint: Optional[str],
        option_hint: Optional[str],
    ) -> ToolResult:
        """Generic deterministic shortcut: open menu-like trigger, then pick target option."""
        trigger = (trigger_hint or "").strip()
        option = (option_hint or "").strip()
        escaped_trigger = trigger.replace("\\", "\\\\").replace("'", "\\'")
        escaped_option = option.replace("\\", "\\\\").replace("'", "\\'")
        script = f"""() => {{
            const triggerHint = '{escaped_trigger}'.trim().toLowerCase();
            const targetOption = '{escaped_option}'.trim().toLowerCase();
            const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();
            const isVisible = (el) => {{
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                const style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                return true;
            }};
            const clickEl = (el) => {{
                el.dispatchEvent(new MouseEvent('mouseover', {{ bubbles: true }}));
                el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
                el.click();
            }};

            const all = document.querySelectorAll('button,[role=\"button\"],a,div,span,li');
            const triggerKeywords = ['new', 'create', 'add', '新增', '创建', '新建'];
            let clickedTrigger = false;
            let matchedTriggerText = '';
            for (const el of all) {{
                if (!isVisible(el)) continue;
                const txt = norm(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                if (!txt) continue;
                let isTrigger = false;
                if (triggerHint && (txt === triggerHint || txt.includes(triggerHint) || triggerHint.includes(txt))) {{
                    isTrigger = true;
                }} else if (!triggerHint) {{
                    isTrigger = triggerKeywords.some(k => txt === k || txt.includes(k));
                }}
                if (isTrigger) {{
                    clickEl(el);
                    clickedTrigger = true;
                    matchedTriggerText = txt;
                    break;
                }}
            }}

            const options = document.querySelectorAll('[role=\"menuitem\"],[role=\"option\"],li,button,a,div,span');
            let clickedOption = false;
            let matchedOptionText = '';
            for (const el of options) {{
                if (!isVisible(el)) continue;
                const txt = norm(el.innerText || el.textContent || '');
                if (!txt) continue;
                if (!targetOption) continue;
                if (txt === targetOption || txt.includes(targetOption) || targetOption.includes(txt)) {{
                    clickEl(el);
                    clickedOption = true;
                    matchedOptionText = txt;
                    break;
                }}
            }}
            return {{
                clicked_trigger: clickedTrigger,
                clicked_option: clickedOption,
                matched_trigger_text: matchedTriggerText,
                matched_option_text: matchedOptionText
            }};
        }}"""
        js_result = await self._browser.console_exec(script)
        if not js_result.success:
            return ToolResult(success=False, message=js_result.message or "shortcut js failed")

        payload = js_result.data if isinstance(js_result.data, dict) else {}
        result_value = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result_value, str):
            try:
                result_value = json.loads(result_value)
            except Exception:
                result_value = {}
        if not isinstance(result_value, dict):
            result_value = {}

        clicked_trigger = bool(result_value.get("clicked_trigger"))
        clicked_option = bool(result_value.get("clicked_option"))
        return ToolResult(
            success=clicked_trigger or clicked_option,
            message=None if (clicked_trigger or clicked_option) else "shortcut could not find trigger/option controls",
            data={
                "clicked_trigger": clicked_trigger,
                "clicked_option": clicked_option,
                "trigger_hint": trigger,
                "option_hint": option,
                "matched_trigger_text": result_value.get("matched_trigger_text", ""),
                "matched_option_text": result_value.get("matched_option_text", ""),
            },
        )

    async def _try_goal_shortcuts(
        self,
        goal: str,
        round_idx: int,
        history: List[BrowserEngineTrace],
    ) -> bool:
        if not goal:
            return False
        if round_idx > 3:
            return False
        if any(item.action.startswith("shortcut_") for item in history):
            return False
        if not re.search(r"(点击|选择|菜单|下拉|select|dropdown|menu|click)", goal, re.IGNORECASE):
            return False

        candidates = self._extract_quoted_candidates(goal)
        trigger_hint = candidates[0] if len(candidates) >= 1 else None
        option_hint = candidates[1] if len(candidates) >= 2 else None
        if not option_hint and len(candidates) == 1:
            option_hint = candidates[0]

        shortcut = await self._shortcut_click_menu_and_option(trigger_hint, option_hint)
        if not shortcut.success:
            return False

        detail_data = shortcut.data if isinstance(shortcut.data, dict) else {}
        history.append(
            BrowserEngineTrace(
                round=round_idx,
                action="shortcut_menu_option",
                reason="generic deterministic menu-option handler",
                status="ok",
                detail=json.dumps(detail_data, ensure_ascii=False),
                verify=True,
            )
        )
        return True

    async def _execute_action(
        self,
        action: BrowserEngineAction,
        perception: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        try:
            if action.action == "navigate":
                if not action.url:
                    return ToolResult(success=False, message="navigate requires url")
                return await self._browser.navigate(action.url)

            if action.action == "click":
                if action.text:
                    quick = await self._click_by_text_fallback(action.text)
                    if quick.success:
                        return quick
                if action.index is None:
                    if action.text:
                        return await self._click_by_text_fallback(action.text)
                    return ToolResult(success=False, message="click requires index or text")
                result = await self._browser.click(index=action.index)
                if not result.success and not action.text and perception:
                    try:
                        elems = perception.get("interactive_elements", [])
                        if isinstance(elems, list) and action.index < len(elems):
                            hint = str(elems[action.index])
                            # Format: "12:<button>text</button>" -> extract text between > and <
                            if ">" in hint and "<" in hint:
                                extracted = hint.split(">", 1)[1].rsplit("<", 1)[0].strip()
                                if extracted:
                                    fallback = await self._click_by_text_fallback(extracted)
                                    if fallback.success:
                                        return fallback
                    except Exception:
                        pass
                if not result.success and action.text:
                    fallback = await self._click_by_text_fallback(action.text)
                    if fallback.success:
                        return fallback
                return result

            if action.action == "hover_click":
                if action.text:
                    quick = await self._click_by_text_fallback(action.text)
                    if quick.success:
                        return quick
                if action.index is None:
                    if action.text:
                        return await self._click_by_text_fallback(action.text)
                    return ToolResult(success=False, message="hover_click requires index or text")
                hover_result = await self._browser.hover(index=action.index)
                if not hover_result.success:
                    return hover_result
                click_result = await self._browser.click(index=action.index)
                if not click_result.success and action.text:
                    fallback = await self._click_by_text_fallback(action.text)
                    if fallback.success:
                        return fallback
                return click_result

            if action.action == "input":
                if action.input_text is None:
                    return ToolResult(success=False, message="input requires input_text")
                return await self._browser.input(
                    text=action.input_text,
                    press_enter=bool(action.press_enter),
                    index=action.index,
                )

            if action.action == "set_date_field":
                if not action.field_label:
                    return ToolResult(success=False, message="set_date_field requires field_label")
                return await self.set_date_field(
                    field_label=action.field_label,
                    date_expr=action.date_expr or action.field_value or "today",
                )

            if action.action == "set_select_field":
                if not action.field_label or not action.field_value:
                    return ToolResult(success=False, message="set_select_field requires field_label and field_value")
                return await self.set_select_field(
                    field_label=action.field_label,
                    field_value=action.field_value,
                )

            if action.action == "set_people_field":
                if not action.field_label or not action.field_value:
                    return ToolResult(success=False, message="set_people_field requires field_label and field_value")
                return await self.set_people_field(
                    field_label=action.field_label,
                    field_value=action.field_value,
                )

            if action.action == "press_key":
                if not action.key:
                    return ToolResult(success=False, message="press_key requires key")
                return await self._browser.press_key(action.key)

            if action.action == "scroll_down":
                return await self._browser.scroll_down()

            if action.action == "scroll_up":
                return await self._browser.scroll_up()

            if action.action == "wait_for_selector":
                if not action.selector:
                    return ToolResult(success=False, message="wait_for_selector requires selector")
                return await self._browser.wait_for_selector(
                    selector=action.selector,
                    text_contains=action.text_contains,
                    timeout_ms=6000,
                )

            if action.action == "finish":
                return ToolResult(success=True, message="goal finished by planner")

            if action.action == "ask_user":
                return ToolResult(success=False, message="planner asked user intervention")

            return ToolResult(success=False, message=f"unknown action: {action.action}")
        except Exception as exc:
            return ToolResult(success=False, message=f"execute action failed: {exc}")

    async def _verify_action(
        self,
        action: BrowserEngineAction,
        result: ToolResult,
        before_perception: Optional[Dict[str, Any]] = None,
        after_perception: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not result.success:
            return False
        if action.action in {"finish"}:
            return True
        if action.selector:
            verify = await self._browser.wait_for_selector(
                selector=action.selector,
                text_contains=action.text_contains,
                timeout_ms=3500,
            )
            if not verify.success:
                return False

        # For mutating UI actions, require observable progress when no explicit selector is supplied.
        if action.action in {
            "click",
            "hover_click",
            "input",
            "set_date_field",
            "set_select_field",
            "set_people_field",
            "scroll_down",
            "scroll_up",
            "navigate",
        }:
            if before_perception and after_perception:
                before_fp = self._perception_fingerprint(before_perception)
                after_fp = self._perception_fingerprint(after_perception)
                if action.action == "navigate":
                    return before_fp != after_fp or (before_perception.get("url") != after_perception.get("url"))
                if before_fp == after_fp:
                    return False
        return True

    async def _recover(self, action: BrowserEngineAction, result: ToolResult) -> ToolResult:
        if action.text:
            fallback = await self._click_by_text_fallback(action.text)
            if fallback.success:
                return fallback
        if action.action in {"click", "hover_click"} and action.index is not None:
            for offset in (1, -1, 2, -2):
                probe = action.index + offset
                if probe < 0:
                    continue
                retry = await self._browser.click(index=probe)
                if retry.success:
                    return retry
        # Last recovery: scroll and allow next round to re-observe.
        await self._browser.scroll_down()
        return ToolResult(success=False, message=result.message or "recovery exhausted")

    async def execute_goal(
        self,
        goal: str,
        expected_result: Optional[str] = None,
        extra_context: Optional[str] = None,
        max_steps: int = 12,
        task_timeout_seconds: int = 300,
    ) -> ToolResult:
        if not goal or not goal.strip():
            return ToolResult(success=False, message="goal is required")

        started_at = time.time()
        history: List[BrowserEngineTrace] = []
        recoveries = 0
        no_progress_rounds = 0
        action_signature_hits: Dict[str, int] = {}

        for round_idx in range(1, max_steps + 1):
            if time.time() - started_at > task_timeout_seconds:
                return ToolResult(
                    success=False,
                    message=f"browser_engine timeout after {task_timeout_seconds}s",
                    data={"trace": [item.model_dump() for item in history], "recoveries": recoveries},
                )

            use_vision_this_round = (
                self._vision_runtime_enabled
                and (round_idx <= self._vision_round_limit or no_progress_rounds >= 1)
            )
            perception = await self._perceive(include_screenshot=use_vision_this_round)
            if not perception.get("ok"):
                history.append(
                    BrowserEngineTrace(
                        round=round_idx,
                        action="observe",
                        status="failed",
                        detail=perception.get("view_error", "view_page failed"),
                    )
                )
                continue

            if await self._try_goal_shortcuts(goal.strip(), round_idx, history):
                no_progress_rounds = 0
                continue

            action = await self._plan_action(
                goal=goal.strip(),
                expected_result=(expected_result or "").strip(),
                extra_context=(extra_context or "").strip(),
                round_idx=round_idx,
                history=history,
                perception=perception,
            )

            if action.action == "finish":
                history.append(
                    BrowserEngineTrace(
                        round=round_idx,
                        action="finish",
                        reason=action.reason,
                        status="finish",
                        detail=action.success_criteria or "planner decided goal is complete",
                        verify=True,
                    )
                )
                return ToolResult(
                    success=True,
                    message=action.success_criteria or "BrowserEngine completed goal",
                    data={
                        "trace": [item.model_dump() for item in history],
                        "rounds": round_idx,
                        "recoveries": recoveries,
                        "final_url": perception.get("url", ""),
                    },
                )

            if action.action == "ask_user":
                history.append(
                    BrowserEngineTrace(
                        round=round_idx,
                        action="ask_user",
                        reason=action.reason,
                        status="ask_user",
                        detail=action.success_criteria or "user intervention required",
                        verify=False,
                    )
                )
                return ToolResult(
                    success=False,
                    message=action.success_criteria or "Need user intervention for this step",
                    data={"trace": [item.model_dump() for item in history], "recoveries": recoveries},
                )

            signature = json.dumps(
                {
                    "action": action.action,
                    "url": action.url,
                    "index": action.index,
                    "text": action.text,
                    "field_label": action.field_label,
                    "field_value": action.field_value,
                    "date_expr": action.date_expr,
                    "selector": action.selector,
                    "text_contains": action.text_contains,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            action_signature_hits[signature] = action_signature_hits.get(signature, 0) + 1

            if action_signature_hits[signature] >= 4:
                history.append(
                    BrowserEngineTrace(
                        round=round_idx,
                        action=action.action,
                        reason=action.reason,
                        status="failed",
                        detail="stopped repeating identical action signature",
                        verify=False,
                    )
                )
                return ToolResult(
                    success=False,
                    message="BrowserEngine aborted: repeated identical action without progress",
                    data={
                        "trace": [item.model_dump() for item in history],
                        "rounds": round_idx,
                        "recoveries": recoveries,
                        "final_url": perception.get("url", ""),
                    },
                )

            action_result = await self._execute_action(action, perception=perception)
            after_perception = await self._perceive(include_screenshot=False)
            verified = await self._verify_action(
                action=action,
                result=action_result,
                before_perception=perception,
                after_perception=after_perception,
            )

            if verified:
                if self._perception_fingerprint(perception) == self._perception_fingerprint(after_perception):
                    no_progress_rounds += 1
                else:
                    no_progress_rounds = 0
                history.append(
                    BrowserEngineTrace(
                        round=round_idx,
                        action=action.action,
                        reason=action.reason,
                        status="ok",
                        detail=action_result.message or "",
                        verify=True,
                    )
                )
                logger.info(
                    "BrowserEngine round=%s action=%s verified=true no_progress_rounds=%s url=%s",
                    round_idx,
                    action.action,
                    no_progress_rounds,
                    after_perception.get("url", ""),
                )
                if no_progress_rounds >= 3:
                    history.append(
                        BrowserEngineTrace(
                            round=round_idx,
                            action="guard",
                            reason="detected repeated verified actions with no visible progress",
                            status="failed",
                            detail="no-progress guard triggered",
                            verify=False,
                        )
                    )
                    return ToolResult(
                        success=False,
                        message="BrowserEngine no-progress guard triggered",
                        data={
                            "trace": [item.model_dump() for item in history],
                            "rounds": round_idx,
                            "recoveries": recoveries,
                            "final_url": after_perception.get("url", ""),
                        },
                    )
                continue

            recovered_result = await self._recover(action, action_result)
            recoveries += 1
            recovery_after_perception = await self._perceive(include_screenshot=False)
            recovered = await self._verify_action(
                action=action,
                result=recovered_result,
                before_perception=perception,
                after_perception=recovery_after_perception,
            )
            if recovered:
                no_progress_rounds = 0

            history.append(
                BrowserEngineTrace(
                    round=round_idx,
                    action=action.action,
                    reason=action.reason,
                    status="recovered" if recovered else "failed",
                    detail=recovered_result.message or action_result.message or "step failed",
                    verify=recovered,
                )
            )
            logger.info(
                "BrowserEngine round=%s action=%s verified=false recovered=%s msg=%s",
                round_idx,
                action.action,
                recovered,
                (recovered_result.message or action_result.message or "")[:200],
            )

            if not recovered and sum(1 for x in history[-3:] if x.status == "failed") >= 3:
                return ToolResult(
                    success=False,
                    message="BrowserEngine aborted after repeated failures",
                    data={
                        "trace": [item.model_dump() for item in history],
                        "rounds": round_idx,
                        "recoveries": recoveries,
                        "final_url": perception.get("url", ""),
                    },
                )

        return ToolResult(
            success=False,
            message=f"BrowserEngine reached max_steps={max_steps}",
            data={"trace": [item.model_dump() for item in history], "recoveries": recoveries},
        )
