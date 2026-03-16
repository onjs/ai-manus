from typing import AsyncGenerator, Optional, List
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.execution import EXECUTION_SYSTEM_PROMPT, EXECUTION_PROMPT, SUMMARIZE_PROMPT
from app.domain.models.event import (
    BaseEvent,
    StepEvent,
    StepStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.services.tools.base import BaseToolkit
import logging

logger = logging.getLogger(__name__)


class ExecutionAgent(BaseAgent):
    """
    Execution agent class, defining the basic behavior of execution
    """

    name: str = "execution"
    system_prompt: str = SYSTEM_PROMPT + EXECUTION_SYSTEM_PROMPT
    format: str = "json_object"

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        tools: List[BaseToolkit],
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            tools=tools
        )

    @staticmethod
    def _build_step_ledger(plan: Plan, max_steps: int = 20) -> str:
        rows: List[str] = []
        for i, s in enumerate(plan.steps):
            if i >= max_steps:
                rows.append(f"- ... and {len(plan.steps) - max_steps} more steps")
                break
            status = str(s.status)
            desc = (s.description or "").strip().replace("\n", " ")
            if len(desc) > 120:
                desc = desc[:117] + "..."
            rows.append(f"- [{status}] {s.id}: {desc}")
        return "\n".join(rows) if rows else "- (no planned steps)"
    
    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
        message = EXECUTION_PROMPT.format(
            step=step.description,
            goal_anchor=plan.goal or "(no explicit goal)",
            step_ledger=self._build_step_ledger(plan),
            message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language
        )
        step.status = ExecutionStatus.RUNNING
        yield StepEvent(status=StepStatus.STARTED, step=step)
        async for event in self.execute(message):
            if isinstance(event, ErrorEvent):
                step.status = ExecutionStatus.FAILED
                step.error = event.error
                yield StepEvent(status=StepStatus.FAILED, step=step)
            elif isinstance(event, MessageEvent):
                try:
                    step.status = ExecutionStatus.COMPLETED
                    parsed_response = await self._parse_json(event.message)
                    new_step = Step.model_validate(parsed_response)
                    step.success = new_step.success
                    step.result = new_step.result
                    step.attachments = new_step.attachments
                    yield StepEvent(status=StepStatus.COMPLETED, step=step)
                    if step.result:
                        yield MessageEvent(message=step.result)
                except Exception as e:
                    step.status = ExecutionStatus.FAILED
                    step.error = f"Invalid step JSON output: {e}"
                    yield ErrorEvent(error=step.error)
                    yield StepEvent(status=StepStatus.FAILED, step=step)
                continue
            elif isinstance(event, ToolEvent):
                if event.function_name == "message_ask_user":
                    if event.status == ToolStatus.CALLING:
                        yield MessageEvent(message=event.function_args.get("text") or "")
                    elif event.status == ToolStatus.CALLED:
                        yield WaitEvent()
                        return
                    continue
            yield event
        step.status = ExecutionStatus.COMPLETED

    async def summarize(self) -> AsyncGenerator[BaseEvent, None]:
        message = SUMMARIZE_PROMPT
        async for event in self.execute(message):
            if isinstance(event, MessageEvent):
                logger.debug(f"Execution agent summary: {event.message}")
                try:
                    parsed_response = await self._parse_json(event.message)
                    message = Message.model_validate(parsed_response)
                    attachments = [FileInfo(file_path=file_path) for file_path in message.attachments]
                    yield MessageEvent(message=message.message, attachments=attachments)
                except Exception as e:
                    logger.warning(f"Execution summary JSON parse failed: {e}")
                    # Fallback to raw message to avoid failing the whole task.
                    yield MessageEvent(message=event.message or "")
                continue
            yield event
