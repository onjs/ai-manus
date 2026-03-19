from types import SimpleNamespace
from typing import Optional

import pytest

from app.domain.models.session import Session
from app.domain.services.runtime.factory import AgentRuntimeFactory
from app.domain.services.runtime.gateway import GatewayAgentRuntime


class FakeTask:
    _last_runner = None

    def __init__(self, task_id: str = "task-1"):
        self._id = task_id

    @property
    def id(self) -> str:
        return self._id

    @classmethod
    def create(cls, runner):
        cls._last_runner = runner
        return cls("task-1")

    @classmethod
    async def destroy(cls) -> None:
        return None

    @classmethod
    def get(cls, task_id: str) -> Optional["FakeTask"]:
        return None


class FakeSessionRepository:
    def __init__(self):
        self.saved_sessions = []

    async def save(self, session: Session):
        self.saved_sessions.append(session.id)


class FakeSandbox:
    instances = {}

    def __init__(self, sandbox_id: str = "sandbox-1"):
        self.id = sandbox_id

    @classmethod
    async def get(cls, sandbox_id: str):
        return cls.instances.get(sandbox_id)

    @classmethod
    async def create(cls):
        sbx = cls("sandbox-new")
        cls.instances[sbx.id] = sbx
        return sbx


class DummyRunner:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _build_factory(gateway_client=None):
    return AgentRuntimeFactory(
        task_cls=FakeTask,
        sandbox_cls=FakeSandbox,
        session_repository=FakeSessionRepository(),
        gateway_client=gateway_client,
    )


def test_runtime_factory_builds_gateway_runtime():
    runtime = _build_factory(gateway_client=SimpleNamespace()).create()
    assert isinstance(runtime, GatewayAgentRuntime)


def test_runtime_factory_requires_gateway_client():
    with pytest.raises(RuntimeError, match="GATEWAY_BASE_URL"):
        _build_factory(gateway_client=None).create()


@pytest.mark.asyncio
async def test_gateway_runtime_create_task_creates_sandbox_and_binds_task(monkeypatch):
    from app.domain.services.runtime import gateway as gateway_runtime_module

    monkeypatch.setattr(gateway_runtime_module, "GatewayTaskRunner", DummyRunner)

    session_repository = FakeSessionRepository()
    runtime = GatewayAgentRuntime(
        task_cls=FakeTask,
        sandbox_cls=FakeSandbox,
        session_repository=session_repository,
        gateway_client=SimpleNamespace(),
    )
    session = Session(id="s3", user_id="u1", agent_id="a1")

    task = await runtime.create_task(session)

    assert task.id == "task-1"
    assert session.sandbox_id == "sandbox-new"
    assert session.task_id == "task-1"
    assert session_repository.saved_sessions.count("s3") >= 2
