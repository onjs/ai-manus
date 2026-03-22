import pytest

from app.domain.models.event import DoneEvent, PlanEvent, PlanStatus, StepEvent, StepStatus, TitleEvent, WaitEvent
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.models.session import Session, SessionStatus
from app.domain.services.flows.plan_act import PlanActFlow
from app.infrastructure.repositories.in_memory_agent_repository import in_memory_agent_repository


class FakeSessionRepository:
    def __init__(self, session: Session | None) -> None:
        self._session = session
        self.updated_statuses: list[SessionStatus] = []

    async def find_by_id(self, session_id: str):  # noqa: ANN001
        if self._session and self._session.id == session_id:
            return self._session
        return None

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        if self._session and self._session.id == session_id:
            self._session.status = status
            self.updated_statuses.append(status)


class FakeSandbox:
    pass


class FakeBrowser:
    pass


class FakeMCPToolkit:
    name = "mcp"


class FakePlanner:
    rollback_called = 0

    def __init__(self, **kwargs):  # noqa: ANN003
        _ = kwargs

    async def create_plan(self, message):  # noqa: ANN001
        _ = message
        plan = Plan(
            title="demo",
            goal="g",
            message="planned",
            steps=[Step(id="s1", description="step-1")],
        )
        yield PlanEvent(status=PlanStatus.CREATED, plan=plan)

    async def update_plan(self, plan, step):  # noqa: ANN001
        _ = step
        step.status = ExecutionStatus.COMPLETED
        step.success = True
        yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)

    async def roll_back(self, message):  # noqa: ANN001
        _ = message
        FakePlanner.rollback_called += 1


class FakeExecution:
    rollback_called = 0

    def __init__(self, **kwargs):  # noqa: ANN003
        _ = kwargs

    async def execute_step(self, plan, step, message):  # noqa: ANN001
        _ = (plan, message)
        yield WaitEvent()
        step.status = ExecutionStatus.COMPLETED
        step.success = True
        yield StepEvent(status=StepStatus.COMPLETED, step=step)

    async def summarize(self):
        if False:
            yield None

    async def compact_memory(self):
        return None

    async def roll_back(self, message):  # noqa: ANN001
        _ = message
        FakeExecution.rollback_called += 1


@pytest.mark.asyncio
async def test_plan_act_flow_emits_wait_and_completes(monkeypatch):
    from app.domain.services.flows import plan_act as plan_act_module

    monkeypatch.setattr(plan_act_module, "PlannerAgent", FakePlanner)
    monkeypatch.setattr(plan_act_module, "ExecutionAgent", FakeExecution)

    session = Session(id="s1", user_id="u1", agent_id="a1", status=SessionStatus.PENDING)
    session_repo = FakeSessionRepository(session)

    flow = PlanActFlow(
        agent_id="a1",
        agent_repository=in_memory_agent_repository,
        session_id="s1",
        session_repository=session_repo,
        sandbox=FakeSandbox(),
        browser=FakeBrowser(),
        mcp_tool=FakeMCPToolkit(),
        model_kwargs={},
    )

    out = []
    async for event in flow.run(Message(message="need login", attachments=[])):
        out.append(event)

    assert any(isinstance(event, TitleEvent) for event in out)
    assert any(isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED for event in out)
    assert any(isinstance(event, WaitEvent) for event in out)
    assert any(isinstance(event, DoneEvent) for event in out)
    assert session_repo.updated_statuses == [SessionStatus.RUNNING]


@pytest.mark.asyncio
async def test_plan_act_flow_rolls_back_when_session_not_pending(monkeypatch):
    from app.domain.services.flows import plan_act as plan_act_module

    FakePlanner.rollback_called = 0
    FakeExecution.rollback_called = 0
    monkeypatch.setattr(plan_act_module, "PlannerAgent", FakePlanner)
    monkeypatch.setattr(plan_act_module, "ExecutionAgent", FakeExecution)

    session = Session(id="s1", user_id="u1", agent_id="a1", status=SessionStatus.RUNNING)
    session_repo = FakeSessionRepository(session)

    flow = PlanActFlow(
        agent_id="a1",
        agent_repository=in_memory_agent_repository,
        session_id="s1",
        session_repository=session_repo,
        sandbox=FakeSandbox(),
        browser=FakeBrowser(),
        mcp_tool=FakeMCPToolkit(),
        model_kwargs={},
    )

    async for _ in flow.run(Message(message="resume", attachments=[])):
        pass

    assert FakePlanner.rollback_called == 1
    assert FakeExecution.rollback_called == 1


@pytest.mark.asyncio
async def test_plan_act_flow_raises_when_session_missing(monkeypatch):
    from app.domain.services.flows import plan_act as plan_act_module

    monkeypatch.setattr(plan_act_module, "PlannerAgent", FakePlanner)
    monkeypatch.setattr(plan_act_module, "ExecutionAgent", FakeExecution)

    session_repo = FakeSessionRepository(None)

    flow = PlanActFlow(
        agent_id="a1",
        agent_repository=in_memory_agent_repository,
        session_id="missing",
        session_repository=session_repo,
        sandbox=FakeSandbox(),
        browser=FakeBrowser(),
        mcp_tool=FakeMCPToolkit(),
        model_kwargs={},
    )

    with pytest.raises(ValueError, match="Session missing not found"):
        async for _ in flow.run(Message(message="hello", attachments=[])):
            pass
