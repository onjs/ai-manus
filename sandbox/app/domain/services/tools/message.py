from __future__ import annotations

from typing import List, Optional, Union

from langchain.tools import tool

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseToolkit


class MessageToolkit(BaseToolkit):
    name: str = "message"

    @tool(parse_docstring=True)
    async def message_notify_user(self, text: str) -> ToolResult:
        """Send message to user without waiting.

        Args:
            text: User-facing text.
        """
        return ToolResult(success=True, message="OK")

    @tool(parse_docstring=True)
    async def message_ask_user(
        self,
        text: str,
        attachments: Optional[Union[str, List[str]]] = None,
        suggest_user_takeover: Optional[str] = None,
    ) -> ToolResult:
        """Ask user and wait.

        Args:
            text: Question text.
            attachments: Optional attachments list.
            suggest_user_takeover: Optional takeover hint.
        """
        return ToolResult(success=True, data={"text": text, "attachments": attachments})
