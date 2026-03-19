from __future__ import annotations

import asyncio
from typing import Optional

from app.domain.models.agent import Agent
from app.domain.models.memory import Memory
from app.domain.repositories.agent_repository import AgentRepository


class InMemoryAgentRepository(AgentRepository):
    """Sandbox runtime memory repository, scoped in process memory."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = asyncio.Lock()

    async def save(self, agent: Agent) -> None:
        async with self._lock:
            self._agents[agent.id] = agent

    async def find_by_id(self, agent_id: str) -> Optional[Agent]:
        async with self._lock:
            return self._agents.get(agent_id)

    async def add_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        async with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                agent = Agent(id=agent_id)
                self._agents[agent_id] = agent
            agent.memories[name] = memory

    async def get_memory(self, agent_id: str, name: str) -> Memory:
        async with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                agent = Agent(id=agent_id)
                self._agents[agent_id] = agent
            return agent.memories.get(name, Memory(messages=[]))

    async def save_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        await self.add_memory(agent_id, name, memory)


in_memory_agent_repository = InMemoryAgentRepository()
