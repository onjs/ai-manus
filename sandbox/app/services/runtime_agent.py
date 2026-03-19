from __future__ import annotations

from typing import Any, AsyncGenerator

from app.domain.models.event import (
    AgentEvent,
    ErrorEvent,
)
from app.domain.models.message import Message
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.tools import BrowserToolkit, FileToolkit, MCPToolkit, MessageToolkit, SearchToolkit, ShellToolkit
from app.infrastructure.repositories.in_memory_agent_repository import in_memory_agent_repository
from app.services.runtime import RuntimeService


class RuntimeAgentService:
    """LangChain-based runtime agent service (planner + execution + memory)."""

    def __init__(self, gateway_runtime: RuntimeService):
        self._gateway_runtime = gateway_runtime
        self._agent_repository = in_memory_agent_repository

    def _build_flow(self, *, session_id: str, agent_id: str) -> PlanActFlow:
        model_kwargs = self._gateway_runtime.get_chat_model_kwargs(session_id)
        tools = [
            ShellToolkit(),
            BrowserToolkit(),
            FileToolkit(),
            MessageToolkit(),
            MCPToolkit(),
            SearchToolkit(),
        ]
        return PlanActFlow(
            agent_id=agent_id,
            agent_repository=self._agent_repository,
            tools=tools,
            model_kwargs=model_kwargs,
        )

    @staticmethod
    def _dump_any(value: Any) -> Any:
        if hasattr(value, "model_dump") and callable(value.model_dump):
            return value.model_dump(mode="json")
        if hasattr(value, "dict") and callable(value.dict):
            return value.dict()
        return value

    @classmethod
    def _map_event(cls, event: AgentEvent) -> tuple[str, dict[str, Any]]:
        payload = event.model_dump(mode="json")
        payload["type"] = event.type
        return event.type, payload

    async def run(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str,
        sandbox_id: str,
        user_message: str,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        _ = (user_id, sandbox_id)
        try:
            flow = self._build_flow(session_id=session_id, agent_id=agent_id)
            async for event in flow.run(Message(message=user_message, attachments=[])):
                yield self._map_event(event)
        except Exception as e:
            err = ErrorEvent(error=str(e))
            yield self._map_event(err)
