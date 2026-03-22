import logging
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)

class Memory(BaseModel):
    """
    Memory class, defining the basic behavior of memory
    """
    messages: List[Any] = Field(default_factory=list)

    def add_message(self, message: Any) -> None:
        """Add message to memory"""
        self.messages.append(message)
    
    def add_messages(self, messages: List[Any]) -> None:
        """Add messages to memory"""
        self.messages.extend(messages)

    def get_messages(self) -> List[Any]:
        """Get all message history"""
        return self.messages
    
    def get_last_message(self) -> Optional[Any]:
        """Get the last message"""
        if len(self.messages) > 0:  
            return self.messages[-1]
        return None
    
    def roll_back(self) -> None:
        """Roll back memory"""
        self.messages = self.messages[:-1]
    
    def compact(self) -> None:
        """Compact memory"""
        for message in self.messages:
            message_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
            message_name = message.get("name") if isinstance(message, dict) else getattr(message, "name", None)
            if message_type == "tool" and message_name in {"browser_view", "browser_navigate"}:
                redacted_content = ToolResult(success=True, data='(removed)').model_dump_json()
                if isinstance(message, dict):
                    message["content"] = redacted_content
                else:
                    message.content = redacted_content
                logger.debug(f"Removed tool result from memory: {message_name}")

    @property
    def empty(self) -> bool:
        """Check if memory is empty"""
        return len(self.messages) == 0
