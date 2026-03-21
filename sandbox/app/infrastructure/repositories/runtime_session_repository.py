from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Optional

from app.domain.models.event import BaseEvent, PlanEvent, PlanStatus
from app.domain.models.file import FileInfo
from app.domain.models.plan import Plan
from app.domain.models.session import Session, SessionStatus
from app.domain.repositories.session_repository import SessionRepository


class RuntimeSessionRepository(SessionRepository):
    """In-process session repository for sandbox runtime flow compatibility."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def seed(
        self,
        *,
        session_id: str,
        user_id: str,
        agent_id: str,
        sandbox_id: str,
        status: str,
        last_plan: dict | None,
    ) -> Session:
        mapped_status = self._map_status(status)
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = Session(
                    id=session_id,
                    user_id=user_id,
                    sandbox_id=sandbox_id,
                    agent_id=agent_id,
                    status=mapped_status,
                )
                self._sessions[session_id] = session
            else:
                session.status = mapped_status
                session.updated_at = datetime.now(UTC)

            if last_plan is not None:
                plan = Plan.model_validate(last_plan)
                session.events = [
                    event
                    for event in session.events
                    if not isinstance(event, PlanEvent)
                ]
                session.events.append(PlanEvent(status=PlanStatus.CREATED, plan=plan))

            return session

    @staticmethod
    def _map_status(status: str) -> SessionStatus:
        raw = (status or "").strip().lower()
        if raw == SessionStatus.RUNNING.value:
            return SessionStatus.RUNNING
        if raw == SessionStatus.WAITING.value:
            return SessionStatus.WAITING
        if raw == SessionStatus.COMPLETED.value:
            return SessionStatus.COMPLETED
        return SessionStatus.PENDING

    async def save(self, session: Session) -> None:
        async with self._lock:
            self._sessions[session.id] = session

    async def find_by_id(self, session_id: str) -> Optional[Session]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def find_by_user_id(self, user_id: str) -> list[Session]:
        async with self._lock:
            return [s for s in self._sessions.values() if s.user_id == user_id]

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Optional[Session]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and session.user_id == user_id:
                return session
            return None

    async def update_title(self, session_id: str, title: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.title = title
                session.updated_at = datetime.now(UTC)

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.latest_message = message
                session.latest_message_at = timestamp
                session.updated_at = datetime.now(UTC)

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.events.append(event)
                session.updated_at = datetime.now(UTC)

    async def add_file(self, session_id: str, file_info: FileInfo) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.files.append(file_info)
                session.updated_at = datetime.now(UTC)

    async def remove_file(self, session_id: str, file_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.files = [f for f in session.files if f.id != file_id]
                session.updated_at = datetime.now(UTC)

    async def get_file_by_path(self, session_id: str, file_path: str) -> Optional[FileInfo]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            for item in session.files:
                if item.file_path == file_path:
                    return item
            return None

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.status = status
                session.updated_at = datetime.now(UTC)

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.unread_message_count = count
                session.updated_at = datetime.now(UTC)

    async def increment_unread_message_count(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.unread_message_count += 1
                session.updated_at = datetime.now(UTC)

    async def decrement_unread_message_count(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.unread_message_count = max(0, session.unread_message_count - 1)
                session.updated_at = datetime.now(UTC)

    async def update_shared_status(self, session_id: str, is_shared: bool) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.is_shared = is_shared
                session.updated_at = datetime.now(UTC)

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def get_all(self) -> list[Session]:
        async with self._lock:
            return list(self._sessions.values())


runtime_session_repository = RuntimeSessionRepository()
