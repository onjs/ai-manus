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
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.services.tools.base import BaseToolkit
import logging
import re

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
        model_kwargs: dict | None = None,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            tools=tools,
            model_kwargs=model_kwargs,
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

    @staticmethod
    def _infer_blocked_reason(text: str) -> Optional[str]:
        raw = (text or "").strip()
        if not raw:
            return None
        lowered = raw.lower()

        rules = [
            (r"(captcha|验证码|人机验证|滑块)", "captcha_required"),
            (r"(login|log in|sign in|登录|扫码登录|账号登录)", "login_required"),
            (r"(permission|forbidden|access denied|无权限|权限不足|403)", "permission_denied"),
            (r"(rate limit|too many requests|429|频率限制|限流)", "rate_limited"),
            (r"(timeout|timed out|network|连接失败|超时|服务不可用|502|503|504)", "system_unavailable"),
            (r"(required|missing|不能为空|必填|缺少|未提供)", "missing_prerequisite"),
            (r"(manual|人工|请确认|审批|approval|confirm)", "manual_confirmation_required"),
        ]
        for pattern, reason in rules:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return reason
        return "unknown_blocked"
    
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
                step.blocked_reason = self._infer_blocked_reason(event.error)
                yield StepEvent(status=StepStatus.FAILED, step=step)
            elif isinstance(event, MessageEvent):
                try:
                    step.status = ExecutionStatus.COMPLETED
                    parsed_response = await self._parse_json(event.message)
                    new_step = Step.model_validate(parsed_response)
                    step.success = new_step.success
                    step.result = new_step.result
                    step.attachments = new_step.attachments
                    blocked_reason = parsed_response.get("blocked_reason") if isinstance(parsed_response, dict) else None
                    if isinstance(blocked_reason, str) and blocked_reason.strip():
                        step.blocked_reason = blocked_reason.strip()
                    elif step.success is False:
                        step.blocked_reason = self._infer_blocked_reason(step.result or "")
                    else:
                        step.blocked_reason = None
                    yield StepEvent(status=StepStatus.COMPLETED, step=step)
                    if step.result:
                        yield MessageEvent(message=step.result)
                except Exception as e:
                    # If model returns a human-readable blocked explanation instead of strict JSON,
                    # surface that explanation to user and finish this step with success=False.
                    raw_message = (event.message or "").strip()
                    if raw_message:
                        step.status = ExecutionStatus.COMPLETED
                        step.success = False
                        step.result = raw_message
                        step.error = None
                        step.blocked_reason = self._infer_blocked_reason(raw_message)
                        yield StepEvent(status=StepStatus.COMPLETED, step=step)
                        yield MessageEvent(message=raw_message)
                        return

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
        if step.status == ExecutionStatus.RUNNING:
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
