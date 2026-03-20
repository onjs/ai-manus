from __future__ import annotations

import logging
import time
from enum import Enum
from typing import AsyncGenerator, Optional

from app.core.config import settings
from app.domain.models.event import BaseEvent, DoneEvent, ErrorEvent, MessageEvent, PlanEvent, PlanStatus, TitleEvent, WaitEvent
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.flows.base import BaseFlow
from app.domain.services.tools.base import BaseToolkit

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    UPDATING = "updating"


class AgentLoopError(RuntimeError):
    """Deterministic flow error carrying a stable classification code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PlanActFlow(BaseFlow):
    """Sandbox runtime plan-act loop aligned with ai-manus flow states."""

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        tools: list[BaseToolkit],
        model_kwargs: dict,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._max_rounds = int(settings.AGENT_LOOP_MAX_ROUNDS)
        self._timeout_seconds = int(settings.AGENT_LOOP_TIMEOUT_SECONDS)
        self.status = AgentStatus.IDLE
        self.plan = None

        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            tools=tools,
            model_kwargs=model_kwargs,
        )
        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            tools=tools,
            model_kwargs=model_kwargs,
        )

    def _assert_not_timeout(self, started_at: float) -> None:
        elapsed = time.monotonic() - started_at
        if elapsed > float(self._timeout_seconds):
            raise AgentLoopError(
                "loop_timeout_exceeded",
                f"agent loop timeout exceeded ({self._timeout_seconds}s)",
            )

    async def run(
        self,
        message: Message,
        session_status: str,
        last_plan: dict | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        logger.info("Agent %s start processing message", self._agent_id)
        step = None
        loop_started_at = time.monotonic()
        rounds = 0
        try:
            if session_status not in {"pending", "running", "waiting", "completed"}:
                raise AgentLoopError("session_status_invalid", f"unsupported session status: {session_status}")

            if last_plan is not None:
                self.plan = Plan.model_validate(last_plan)

            if session_status != "pending":
                await self.executor.roll_back(message)
                await self.planner.roll_back(message)

            if session_status == "running":
                self.status = AgentStatus.PLANNING
            elif session_status == "waiting":
                if self.plan is None:
                    raise AgentLoopError("resume_plan_missing", "last_plan is required when resuming from waiting")
                self.status = AgentStatus.EXECUTING

            while True:
                self._assert_not_timeout(loop_started_at)
                if self.status == AgentStatus.IDLE:
                    self.status = AgentStatus.PLANNING
                elif self.status == AgentStatus.PLANNING:
                    async for event in self.planner.create_plan(message):
                        if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                            self.plan = event.plan
                            yield TitleEvent(title=event.plan.title)
                            if event.plan.message is not None:
                                yield MessageEvent(role="assistant", message=event.plan.message or "")
                        yield event
                    self.status = AgentStatus.EXECUTING
                    if self.plan and len(self.plan.steps) == 0:
                        self.status = AgentStatus.COMPLETED

                elif self.status == AgentStatus.EXECUTING:
                    if self.plan is None:
                        raise AgentLoopError("loop_plan_missing", "plan missing in executing state")
                    self.plan.status = ExecutionStatus.RUNNING
                    step = self.plan.get_next_step()
                    if not step:
                        self.status = AgentStatus.SUMMARIZING
                        continue

                    rounds += 1
                    if rounds > self._max_rounds:
                        raise AgentLoopError(
                            "loop_round_limit_exceeded",
                            f"agent loop max rounds exceeded ({self._max_rounds})",
                        )

                    wait_seen = False
                    async for event in self.executor.execute_step(self.plan, step, message):
                        yield event
                        if isinstance(event, WaitEvent):
                            wait_seen = True
                            break
                    if wait_seen:
                        self.status = AgentStatus.IDLE
                        return

                    await self.executor.compact_memory()
                    self.status = AgentStatus.UPDATING

                elif self.status == AgentStatus.UPDATING:
                    if self.plan is None or step is None:
                        raise AgentLoopError("loop_state_error", "plan/step missing in updating state")
                    async for event in self.planner.update_plan(self.plan, step):
                        yield event
                    await self.planner.compact_memory()
                    self.status = AgentStatus.EXECUTING

                elif self.status == AgentStatus.SUMMARIZING:
                    async for event in self.executor.summarize():
                        yield event
                    self.status = AgentStatus.COMPLETED

                elif self.status == AgentStatus.COMPLETED:
                    if self.plan is not None:
                        self.plan.status = ExecutionStatus.COMPLETED
                        yield PlanEvent(status=PlanStatus.COMPLETED, plan=self.plan)
                    self.status = AgentStatus.IDLE
                    break

            yield DoneEvent()
        except AgentLoopError as e:
            self.status = AgentStatus.IDLE
            yield ErrorEvent(error=f"{e.code}: {e}")

    def is_done(self) -> bool:
        return self.status == AgentStatus.IDLE
