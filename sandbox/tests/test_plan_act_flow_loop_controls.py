import pytest

from app.domain.models.event import ErrorEvent, PlanEvent, PlanStatus, StepEvent, StepStatus, TitleEvent, WaitEvent
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.flows.plan_act import PlanActFlow
from app.infrastructure.repositories.in_memory_agent_repository import in_memory_agent_repository


class FakePlannerWait:
    def __init__(self, **kwargs):  # noqa: ANN003
        _ = kwargs

    async def create_plan(self, message):  # noqa: ANN001
        _ = message
        plan = Plan(title="demo", goal="g", steps=[Step(id="s1", description="step-1")])
        yield PlanEvent(status=PlanStatus.CREATED, plan=plan)

    async def update_plan(self, plan, step):  # noqa: ANN001
        _ = (plan, step)
        if False:
            yield None

    async def compact_memory(self):
        return None


class FakeExecutionWait:
    def __init__(self, **kwargs):  # noqa: ANN003
        _ = kwargs

    async def execute_step(self, plan, step, message):  # noqa: ANN001
        _ = (plan, step, message)
        yield WaitEvent()

    async def summarize(self):
        if False:
            yield None

    async def compact_memory(self):
        return None


class FakePlannerLoop:
    def __init__(self, **kwargs):  # noqa: ANN003
        _ = kwargs

    async def create_plan(self, message):  # noqa: ANN001
        _ = message
        plan = Plan(title="loop", goal="g", steps=[Step(id="s1", description="step-1")])
        yield PlanEvent(status=PlanStatus.CREATED, plan=plan)

    async def update_plan(self, plan, step):  # noqa: ANN001
        _ = step
        # Keep producing a new pending step so execution rounds continue.
        next_id = f"s{len(plan.steps) + 1}"
        plan.steps.append(Step(id=next_id, description=f"step-{next_id}"))
        yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)

    async def compact_memory(self):
        return None


class FakeExecutionComplete:
    def __init__(self, **kwargs):  # noqa: ANN003
        _ = kwargs

    async def execute_step(self, plan, step, message):  # noqa: ANN001
        _ = (plan, message)
        step.status = ExecutionStatus.COMPLETED
        step.success = True
        yield StepEvent(status=StepStatus.COMPLETED, step=step)

    async def summarize(self):
        if False:
            yield None

    async def compact_memory(self):
        return None


@pytest.mark.asyncio
async def test_plan_act_flow_stops_without_done_on_wait(monkeypatch):
    from app.domain.services.flows import plan_act as plan_act_module

    monkeypatch.setattr(plan_act_module, "PlannerAgent", FakePlannerWait)
    monkeypatch.setattr(plan_act_module, "ExecutionAgent", FakeExecutionWait)

    flow = PlanActFlow(
        agent_id="a1",
        agent_repository=in_memory_agent_repository,
        tools=[],
        model_kwargs={},
    )

    out = []
    async for event in flow.run(Message(message="need login", attachments=[])):
        out.append(event)

    assert any(isinstance(event, TitleEvent) for event in out)
    assert any(isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED for event in out)
    assert any(isinstance(event, WaitEvent) for event in out)
    assert not any(getattr(event, "type", "") == "done" for event in out)


@pytest.mark.asyncio
async def test_plan_act_flow_emits_classified_error_on_round_limit(monkeypatch):
    from app.domain.services.flows import plan_act as plan_act_module

    monkeypatch.setattr(plan_act_module, "PlannerAgent", FakePlannerLoop)
    monkeypatch.setattr(plan_act_module, "ExecutionAgent", FakeExecutionComplete)

    flow = PlanActFlow(
        agent_id="a1",
        agent_repository=in_memory_agent_repository,
        tools=[],
        model_kwargs={},
    )
    flow._max_rounds = 1  # noqa: SLF001

    out = []
    async for event in flow.run(Message(message="loop", attachments=[])):
        out.append(event)

    assert isinstance(out[-1], ErrorEvent)
    assert "loop_round_limit_exceeded" in out[-1].error


@pytest.mark.asyncio
async def test_plan_act_flow_emits_classified_error_on_timeout(monkeypatch):
    from app.domain.services.flows import plan_act as plan_act_module

    monkeypatch.setattr(plan_act_module, "PlannerAgent", FakePlannerLoop)
    monkeypatch.setattr(plan_act_module, "ExecutionAgent", FakeExecutionComplete)

    flow = PlanActFlow(
        agent_id="a1",
        agent_repository=in_memory_agent_repository,
        tools=[],
        model_kwargs={},
    )
    flow._timeout_seconds = 0  # noqa: SLF001

    out = []
    async for event in flow.run(Message(message="loop", attachments=[])):
        out.append(event)

    assert isinstance(out[-1], ErrorEvent)
    assert "loop_timeout_exceeded" in out[-1].error
