import asyncio
from typing import Any, AsyncGenerator

from app.schemas.runtime_runner import RuntimeRunnerStartRequest
from app.services.runtime import RuntimeService, runtime_service
from app.services.runtime_store import runtime_store

RUNNING_STATUSES = {"starting", "running"}


class RuntimeRunnerService:
    """Session-scoped runner control plane hosted inside sandbox API process."""

    def __init__(self, gateway_runtime: RuntimeService):
        self._gateway_runtime = gateway_runtime
        self._store = runtime_store

    async def start_run(self, request: RuntimeRunnerStartRequest) -> dict[str, Any]:
        if not self._gateway_runtime.has_gateway_config(request.session_id):
            raise ValueError("Gateway runtime is not configured for this session")

        existing = self._store.get_run(request.session_id)
        if existing and existing.get("status") in RUNNING_STATUSES:
            existing["started"] = False
            return existing

        run = self._store.upsert_run(
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_id=request.user_id,
            status="starting",
            message=request.message,
            error=None,
            reset_events=True,
        )
        self._store.enqueue_command(
            session_id=request.session_id,
            command_type="start",
            payload=request.model_dump(),
        )
        run["started"] = True
        return run

    async def cancel_run(self, session_id: str) -> dict[str, Any]:
        run = self._store.get_run(session_id)
        if not run:
            return {"session_id": session_id, "cancelled": False, "reason": "not_found"}
        status = str(run.get("status") or "")
        if status not in RUNNING_STATUSES and status != "cancelling":
            return {"session_id": session_id, "cancelled": False, "reason": "not_running", "status": status}
        self._store.enqueue_command(
            session_id=session_id,
            command_type="cancel",
            payload={"session_id": session_id},
        )
        if status in RUNNING_STATUSES:
            self._store.update_run_status(session_id, status="cancelling", error=None)
        return {"session_id": session_id, "cancelled": True}

    async def clear_run(self, session_id: str) -> dict[str, Any]:
        self._store.enqueue_command(
            session_id=session_id,
            command_type="clear",
            payload={"session_id": session_id},
        )
        return {"session_id": session_id, "cleared": True}

    async def get_status(self, session_id: str) -> dict[str, Any]:
        run = self._store.get_run(session_id)
        if not run:
            return {"session_id": session_id, "status": "not_found"}
        return run

    async def get_events(self, session_id: str, from_seq: int = 1, limit: int = 200) -> dict[str, Any]:
        run = self._store.get_run(session_id)
        if not run:
            return {"session_id": session_id, "status": "not_found", "events": [], "next_seq": from_seq}

        records = self._store.get_events(session_id, from_seq=from_seq, limit=limit)
        next_seq = records[-1]["seq"] + 1 if records else from_seq
        return {
            "session_id": session_id,
            "status": run.get("status", "unknown"),
            "events": records,
            "next_seq": next_seq,
            "last_heartbeat_at": run.get("last_heartbeat_at"),
        }

    async def stream_events(
        self,
        session_id: str,
        from_seq: int = 1,
        limit: int = 200,
        poll_interval: float = 0.2,
        heartbeat_interval: float = 10.0,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        next_seq = max(1, int(from_seq))
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()

        while True:
            result = await self.get_events(session_id, from_seq=next_seq, limit=limit)
            status = str(result.get("status", "unknown"))
            records = result.get("events") or []

            for record in records:
                seq = int(record.get("seq", next_seq))
                next_seq = max(next_seq, seq + 1)
                event_name = str(record.get("event", "error"))
                payload = record.get("data") or {}
                if not isinstance(payload, dict):
                    raise ValueError("runner event payload must be a JSON object")
                yield (
                    event_name,
                    {
                        **payload,
                        "session_id": session_id,
                        "seq": seq,
                        "timestamp": int(record.get("timestamp", 0)),
                    },
                )

            if status in {"completed", "failed", "cancelled", "waiting", "not_found"}:
                return

            now = loop.time()
            if now - last_heartbeat >= heartbeat_interval:
                last_heartbeat = now
                yield (
                    "heartbeat",
                    {
                        "session_id": session_id,
                        "status": status,
                        "next_seq": next_seq,
                    },
                )

            await asyncio.sleep(poll_interval)


runtime_runner_service = RuntimeRunnerService(runtime_service)
