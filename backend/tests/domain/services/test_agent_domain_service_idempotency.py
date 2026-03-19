import re
from datetime import datetime

import pytest

from app.domain.models.event import DoneEvent, ErrorEvent, MessageEvent
from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.services.chat_idempotency_service import ChatIdempotencyService


STREAM_ID_RE = re.compile(r"^\d+-\d+$")


class _FakeRedisAPI:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)
        return True


class _FakeRedisClient:
    def __init__(self):
        self.client = _FakeRedisAPI()


class _FakeInputStream:
    def __init__(self):
        self.put_count = 0

    async def put(self, message):
        self.put_count += 1
        return "1-0"

    async def pop(self):
        return None, None

    async def clear(self):
        return None

    async def is_empty(self):
        return True

    async def size(self):
        return 0

    async def delete_message(self, message_id):
        return True


class _FakeOutputStream:
    def __init__(self, task):
        self._task = task
        self._queue: list[tuple[str, str]] = []
        self.last_start_id = None
        self.start_ids: list[str | None] = []

    async def put(self, message):
        event_id = f"{100 + len(self._queue)}-0"
        self._queue.append((event_id, message))
        return event_id

    async def get(self, start_id=None, block_ms=None):
        self.last_start_id = start_id
        self.start_ids.append(start_id)
        if start_id is not None and start_id not in {"0"} and not STREAM_ID_RE.match(start_id):
            raise RuntimeError("Invalid stream ID specified as stream command argument")
        if self._queue:
            event = self._queue.pop(0)
            if not self._queue:
                self._task._done = True
            return event
        self._task._done = True
        return None, None

    async def get_latest_id(self):
        return "0"

    async def pop(self):
        return None, None

    async def clear(self):
        return None

    async def is_empty(self):
        return not self._queue

    async def size(self):
        return len(self._queue)

    async def delete_message(self, message_id):
        return True


class _FakeTask:
    def __init__(self):
        self._done = True
        self.input_stream = _FakeInputStream()
        self.output_stream = _FakeOutputStream(self)

    @property
    def done(self):
        return self._done

    async def run(self):
        self._done = False
        await self.output_stream.put(
            MessageEvent(role="assistant", message="ok", timestamp=datetime.now()).model_dump_json()
        )
        await self.output_stream.put(DoneEvent(timestamp=datetime.now()).model_dump_json())

    def cancel(self):
        self._done = True
        return True


class _FakeSessionRepository:
    def __init__(self):
        self.session = Session(user_id="u1", agent_id="a1", id="s1", status=SessionStatus.PENDING)

    async def find_by_id_and_user_id(self, session_id, user_id):
        if session_id == self.session.id and user_id == self.session.user_id:
            return self.session
        return None

    async def find_by_id(self, session_id):
        if session_id == self.session.id:
            return self.session
        return None

    async def update_latest_message(self, session_id, message, timestamp):
        self.session.latest_message = message
        self.session.latest_message_at = timestamp

    async def add_event(self, session_id, event):
        self.session.events.append(event)

    async def update_unread_message_count(self, session_id, count):
        self.session.unread_message_count = count

    async def increment_unread_message_count(self, session_id):
        self.session.unread_message_count += 1

    async def update_status(self, session_id, status):
        self.session.status = status


@pytest.mark.asyncio
async def test_chat_requires_request_id_when_message_exists():
    repo = _FakeSessionRepository()
    task = _FakeTask()

    service = AgentDomainService.__new__(AgentDomainService)
    service._session_repository = repo
    service._task_cls = None
    service._chat_idempotency = ChatIdempotencyService(redis_client=_FakeRedisClient())

    async def _create_task(_session):
        return task

    async def _get_task(_session):
        return task

    service._create_task = _create_task
    service._get_task = _get_task

    events = [
        event async for event in service.chat(
            session_id="s1",
            user_id="u1",
            message="hello",
        )
    ]
    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "request_id is required" in events[0].error


@pytest.mark.asyncio
async def test_chat_with_request_id_replays_even_when_event_cursor_is_stream_id():
    repo = _FakeSessionRepository()
    task = _FakeTask()

    service = AgentDomainService.__new__(AgentDomainService)
    service._session_repository = repo
    service._task_cls = None
    service._chat_idempotency = ChatIdempotencyService(redis_client=_FakeRedisClient())

    async def _create_task(_session):
        return task

    async def _get_task(_session):
        return task

    service._create_task = _create_task
    service._get_task = _get_task

    events_first = [
        event async for event in service.chat(
            session_id="s1",
            user_id="u1",
            message="hello",
            latest_event_id="1-0",
            request_id="request-abc-1",
        )
    ]
    assert [event.type for event in events_first] == ["message", "done"]
    assert task.input_stream.put_count == 1

    events_second = [
        event async for event in service.chat(
            session_id="s1",
            user_id="u1",
            message="hello",
            latest_event_id="1-0",
            request_id="request-abc-1",
        )
    ]
    assert [event.type for event in events_second] == ["message", "done"]
    assert task.input_stream.put_count == 1


@pytest.mark.asyncio
async def test_chat_rejects_invalid_event_id():
    repo = _FakeSessionRepository()
    task = _FakeTask()

    service = AgentDomainService.__new__(AgentDomainService)
    service._session_repository = repo
    service._task_cls = None
    service._chat_idempotency = ChatIdempotencyService(redis_client=_FakeRedisClient())

    async def _create_task(_session):
        return task

    async def _get_task(_session):
        return task

    service._create_task = _create_task
    service._get_task = _get_task

    events = [
        event async for event in service.chat(
            session_id="s1",
            user_id="u1",
            message="hello",
            latest_event_id="bad-event-id",
            request_id="req-1",
        )
    ]
    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "event_id must be a valid stream id" in events[0].error


@pytest.mark.asyncio
async def test_chat_rejects_duplicate_running_request():
    repo = _FakeSessionRepository()
    task = _FakeTask()
    fake_redis = _FakeRedisClient()

    service = AgentDomainService.__new__(AgentDomainService)
    service._session_repository = repo
    service._task_cls = None
    service._chat_idempotency = ChatIdempotencyService(redis_client=fake_redis)

    async def _create_task(_session):
        return task

    async def _get_task(_session):
        return task

    service._create_task = _create_task
    service._get_task = _get_task

    started = await service._chat_idempotency.try_start("s1", "request-dup-1")
    assert started is True

    events = [
        event async for event in service.chat(
            session_id="s1",
            user_id="u1",
            message="hello",
            request_id="request-dup-1",
        )
    ]
    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "duplicate request is still running" in events[0].error


@pytest.mark.asyncio
async def test_chat_recreates_task_when_session_running_but_task_missing():
    repo = _FakeSessionRepository()
    repo.session.status = SessionStatus.RUNNING
    task = _FakeTask()

    service = AgentDomainService.__new__(AgentDomainService)
    service._session_repository = repo
    service._task_cls = None
    service._chat_idempotency = ChatIdempotencyService(redis_client=_FakeRedisClient())

    create_calls = {"count": 0}

    async def _create_task(_session):
        create_calls["count"] += 1
        return task

    async def _get_task(_session):
        return None

    service._create_task = _create_task
    service._get_task = _get_task

    events = [
        event
        async for event in service.chat(
            session_id="s1",
            user_id="u1",
            message="hello",
            request_id="req-running-missing-task",
        )
    ]

    assert create_calls["count"] == 1
    assert [event.type for event in events] == ["message", "done"]
