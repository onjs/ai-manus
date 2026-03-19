import logging
import hashlib
import json
from pydantic import BaseModel
from pydantic import Field
from typing import List, Dict, Any, Optional
from app.domain.models.tool_result import ToolResult
from langchain.messages import AnyMessage

logger = logging.getLogger(__name__)

class Memory(BaseModel):
    """
    Memory class, defining the basic behavior of memory
    """
    messages: List[AnyMessage] = Field(default_factory=list)

    def add_message(self, message: AnyMessage) -> None:
        """Add message to memory"""
        self.messages.append(message)
    
    def add_messages(self, messages: List[AnyMessage]) -> None:
        """Add messages to memory"""
        self.messages.extend(messages)

    def get_messages(self) -> List[AnyMessage]:
        """Get all message history"""
        return self.messages
    
    def get_last_message(self) -> Optional[AnyMessage]:
        """Get the last message"""
        if len(self.messages) > 0:  
            return self.messages[-1]
        return None
    
    def roll_back(self) -> None:
        """Roll back memory"""
        self.messages = self.messages[:-1]
    
    @staticmethod
    def _is_compacted(content: str) -> bool:
        return '"compacted": true' in content

    @staticmethod
    def _json_safe_loads(content: str) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 32] + "\n...(truncated)"

    @staticmethod
    def _compact_ref(tool_name: str, original_content: str) -> str:
        # Stable reference allows debugging/audit without carrying full payload every round.
        ref = hashlib.sha1(original_content.encode("utf-8", errors="ignore")).hexdigest()[:12]
        return ToolResult(
            success=True,
            data={
                "compacted": True,
                "tool": tool_name,
                "ref": f"toolmsg:{ref}",
                "summary": "Tool output compacted to control context growth.",
            },
        ).model_dump_json()

    def _clip_browser_payload(self, content: str, max_content_chars: int) -> str:
        payload = self._json_safe_loads(content)
        if not payload:
            return self._truncate_text(content, max_content_chars)

        data = payload.get("data")
        if not isinstance(data, dict):
            return self._truncate_text(content, max_content_chars)

        interactive_elements = data.get("interactive_elements", [])
        if isinstance(interactive_elements, list) and len(interactive_elements) > 120:
            data["interactive_elements"] = interactive_elements[:120]

        page_content = data.get("content")
        if isinstance(page_content, str):
            data["content"] = self._truncate_text(page_content, max_content_chars)

        payload["data"] = data
        return json.dumps(payload, ensure_ascii=False)

    def compact(
        self,
        keep_recent_tool_messages: int = 12,
        browser_content_max_chars: int = 12000,
        generic_tool_max_chars: int = 4000,
    ) -> None:
        """Compact memory with browser-aware strategy.

        Strategy:
        - Keep recent tool outputs (for multi-step continuity).
        - Compact older heavy tool outputs into references.
        - Clip oversized browser payloads instead of removing them.
        """
        tool_indices = [idx for idx, msg in enumerate(self.messages) if msg.type == "tool"]
        keep_from = None
        if len(tool_indices) > keep_recent_tool_messages:
            keep_from = tool_indices[-keep_recent_tool_messages]

        for idx, message in enumerate(self.messages):
            if message.type != "tool":
                continue

            tool_name = getattr(message, "name", "") or "unknown_tool"
            content = message.content if isinstance(message.content, str) else str(message.content)
            if self._is_compacted(content):
                continue

            is_recent = keep_from is None or idx >= keep_from

            if tool_name in {"browser_view", "browser_navigate"}:
                if is_recent:
                    message.content = self._clip_browser_payload(content, browser_content_max_chars)
                else:
                    message.content = self._compact_ref(tool_name, content)
                continue

            if is_recent:
                if len(content) > generic_tool_max_chars:
                    message.content = self._truncate_text(content, generic_tool_max_chars)
            else:
                message.content = self._compact_ref(tool_name, content)

    @property
    def empty(self) -> bool:
        """Check if memory is empty"""
        return len(self.messages) == 0
