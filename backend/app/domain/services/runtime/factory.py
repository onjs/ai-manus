from typing import Type

from app.domain.external.sandbox import Sandbox
from app.domain.external.task import Task
from app.domain.external.file import FileStorage
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.runtime.base import AgentRuntime
from app.domain.services.runtime.gateway import GatewayAgentRuntime
from app.infrastructure.external.gateway.client import GatewayClient


class AgentRuntimeFactory:
    """Factory for runtime construction."""

    def __init__(
        self,
        task_cls: Type[Task],
        sandbox_cls: Type[Sandbox],
        session_repository: SessionRepository,
        file_storage: FileStorage,
        gateway_client: GatewayClient | None = None,
    ):
        self._task_cls = task_cls
        self._sandbox_cls = sandbox_cls
        self._session_repository = session_repository
        self._file_storage = file_storage
        self._gateway_client = gateway_client

    def create(self) -> AgentRuntime:
        if not self._gateway_client:
            raise RuntimeError("Gateway runtime requires GATEWAY_BASE_URL")
        return GatewayAgentRuntime(
            task_cls=self._task_cls,
            sandbox_cls=self._sandbox_cls,
            session_repository=self._session_repository,
            file_storage=self._file_storage,
            gateway_client=self._gateway_client,
        )
