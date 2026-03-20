from typing import Type

from app.domain.external.sandbox import Sandbox
from app.domain.external.task import Task
from app.domain.external.file import FileStorage
from app.domain.models.session import Session
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.gateway_task_runner import GatewayTaskRunner
from app.domain.services.runtime.base import AgentRuntime
from app.infrastructure.external.gateway.client import GatewayClient


class GatewayAgentRuntime(AgentRuntime):
    """Runtime adapter that executes agent loop through gateway service."""

    def __init__(
        self,
        task_cls: Type[Task],
        sandbox_cls: Type[Sandbox],
        session_repository: SessionRepository,
        file_storage: FileStorage,
        gateway_client: GatewayClient,
    ):
        self._task_cls = task_cls
        self._sandbox_cls = sandbox_cls
        self._session_repository = session_repository
        self._file_storage = file_storage
        self._gateway_client = gateway_client

    async def _ensure_sandbox(self, session: Session) -> Sandbox:
        sandbox = None
        if session.sandbox_id:
            try:
                sandbox = await self._sandbox_cls.get(session.sandbox_id)
                await sandbox.ensure_sandbox()
            except Exception:
                sandbox = None

        if not sandbox:
            sandbox = await self._sandbox_cls.create()
            await sandbox.ensure_sandbox()
            session.sandbox_id = sandbox.id
            await self._session_repository.save(session)

        return sandbox

    async def create_task(self, session: Session) -> Task:
        sandbox = await self._ensure_sandbox(session)
        task_runner = GatewayTaskRunner(
            session_id=session.id,
            agent_id=session.agent_id,
            user_id=session.user_id,
            sandbox=sandbox,
            session_repository=self._session_repository,
            file_storage=self._file_storage,
            gateway_client=self._gateway_client,
        )
        task = self._task_cls.create(task_runner)
        session.task_id = task.id
        await self._session_repository.save(session)
        return task
