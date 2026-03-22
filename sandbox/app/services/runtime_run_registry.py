from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


RUNNING_STATUSES = {"starting", "running"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "waiting"}


@dataclass(slots=True)
class RuntimeEventRecord:
    seq: int
    event: str
    data: dict[str, Any]
    timestamp: int


@dataclass(slots=True)
class RunState:
    session_id: str
    agent_id: str
    user_id: str
    status: str
    message: str | None
    error: str | None
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    last_heartbeat_at: int = field(default_factory=lambda: int(time.time()))
    next_seq: int = 1
    task_handle: asyncio.Task[None] | None = None
    events: list[RuntimeEventRecord] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    condition: asyncio.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.condition = asyncio.Condition(self.lock)


class RuntimeRunRegistry:
    """In-memory session run registry used by sandbox runtime APIs."""

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._registry_lock = asyncio.Lock()

    @staticmethod
    def _snapshot(state: RunState) -> dict[str, Any]:
        return {
            "session_id": state.session_id,
            "agent_id": state.agent_id,
            "user_id": state.user_id,
            "status": state.status,
            "message": state.message,
            "error": state.error,
            "created_at": state.created_at,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "last_heartbeat_at": state.last_heartbeat_at,
            "next_seq": state.next_seq,
        }

    async def get_run(self, session_id: str) -> dict[str, Any] | None:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return None
        async with state.lock:
            return self._snapshot(state)

    async def upsert_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str,
        status: str,
        message: str | None,
        error: str | None,
        reset_events: bool = False,
    ) -> dict[str, Any]:
        now = int(time.time())
        async with self._registry_lock:
            state = self._runs.get(session_id)
            if state is None:
                state = RunState(
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    status=status,
                    message=message,
                    error=error,
                    created_at=now,
                )
                self._runs[session_id] = state

        async with state.lock:
            state.agent_id = agent_id
            state.user_id = user_id
            state.status = status
            state.message = message
            state.error = error
            state.last_heartbeat_at = now
            state.started_at = None
            state.finished_at = None
            state.next_seq = 1
            if reset_events:
                state.events.clear()
            state.condition.notify_all()
            return self._snapshot(state)

    async def begin_run(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str,
        message: str | None,
    ) -> tuple[dict[str, Any], bool]:
        """
        Atomically create/reset a run if not running.

        Returns:
            (run_snapshot, started) where started=False means an existing running run is reused.
        """
        now = int(time.time())
        created = False
        async with self._registry_lock:
            state = self._runs.get(session_id)
            if state is None:
                created = True
                state = RunState(
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    status="starting",
                    message=message,
                    error=None,
                    created_at=now,
                )
                self._runs[session_id] = state

        async with state.lock:
            if not created and state.status in RUNNING_STATUSES:
                return self._snapshot(state), False

            state.agent_id = agent_id
            state.user_id = user_id
            state.status = "starting"
            state.message = message
            state.error = None
            state.last_heartbeat_at = now
            state.started_at = None
            state.finished_at = None
            state.next_seq = 1
            state.events.clear()
            state.condition.notify_all()
            return self._snapshot(state), True

    async def update_run_status(
        self,
        session_id: str,
        status: str,
        *,
        error: str | None = None,
        set_started: bool = False,
        set_finished: bool = False,
    ) -> bool:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return False

        now = int(time.time())
        async with state.lock:
            state.status = status
            state.error = error
            state.last_heartbeat_at = now
            if set_started:
                state.started_at = now
            if set_finished:
                state.finished_at = now
            state.condition.notify_all()
        return True

    async def touch_run_heartbeat(self, session_id: str) -> bool:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return False

        async with state.lock:
            state.last_heartbeat_at = int(time.time())
            state.condition.notify_all()
        return True

    async def delete_run(self, session_id: str) -> bool:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return False

        async with state.lock:
            task = state.task_handle
            if task and not task.done():
                task.cancel()
        if task and not task.done():
            await asyncio.gather(task, return_exceptions=True)

        async with self._registry_lock:
            state = self._runs.pop(session_id, None)
        if state is None:
            return False
        async with state.lock:
            state.condition.notify_all()
        return True

    async def attach_task(self, session_id: str, task: asyncio.Task[None] | None) -> bool:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return False
        async with state.lock:
            state.task_handle = task
            state.condition.notify_all()
        return True

    async def cancel_task(self, session_id: str) -> bool:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return False

        async with state.lock:
            task = state.task_handle
            if task and not task.done():
                task.cancel()
            state.condition.notify_all()
        return True

    async def append_event(self, session_id: str, event: str, data: dict[str, Any]) -> int:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            raise ValueError(f"Run not found for session_id={session_id}")

        now = int(time.time())
        async with state.lock:
            seq = state.next_seq
            state.events.append(
                RuntimeEventRecord(
                    seq=seq,
                    event=event,
                    data=data,
                    timestamp=now,
                )
            )
            state.next_seq = seq + 1
            state.last_heartbeat_at = now
            state.condition.notify_all()
            return seq

    async def get_events(
        self,
        session_id: str,
        from_seq: int = 1,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return []

        async with state.lock:
            records = [
                {
                    "seq": item.seq,
                    "event": item.event,
                    "data": item.data,
                    "timestamp": item.timestamp,
                }
                for item in state.events
                if item.seq >= from_seq
            ][:limit]
        return records

    async def wait_for_events(
        self,
        session_id: str,
        next_seq: int,
        timeout: float,
    ) -> bool:
        async with self._registry_lock:
            state = self._runs.get(session_id)
        if state is None:
            return False

        async with state.lock:
            if state.next_seq > next_seq:
                return True
            try:
                await asyncio.wait_for(state.condition.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return False
            return state.next_seq > next_seq


runtime_run_registry = RuntimeRunRegistry()
