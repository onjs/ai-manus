import asyncio
from typing import Any, AsyncGenerator

from app.schemas.runtime_runner import RuntimeRunnerStartRequest
from app.services.runtime import RuntimeService, runtime_service
from app.services.runtime_agent import RuntimeAgentService
from app.services.runtime_run_registry import RUNNING_STATUSES, TERMINAL_STATUSES, runtime_run_registry


class RuntimeRunnerService:
    """Session-scoped runner control plane hosted inside sandbox API process."""

    def __init__(self, gateway_runtime: RuntimeService):
        self._gateway_runtime = gateway_runtime
        self._runtime_agent = RuntimeAgentService(gateway_runtime)
        self._registry = runtime_run_registry

    async def start_run(self, request: RuntimeRunnerStartRequest) -> dict[str, Any]:
        if not self._gateway_runtime.has_gateway_config(request.session_id):
            raise ValueError("Gateway runtime is not configured for this session")

        run, started = await self._registry.begin_run(
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_id=request.user_id,
            message=request.message,
        )
        if not started:
            run["started"] = False
            return run

        task = asyncio.create_task(self._run_session(request))
        await self._registry.attach_task(request.session_id, task)
        run["started"] = True
        return run

    async def cancel_run(self, session_id: str) -> dict[str, Any]:
        run = await self._registry.get_run(session_id)
        if not run:
            return {"session_id": session_id, "cancelled": False, "reason": "not_found"}
        status = str(run.get("status") or "")
        if status not in RUNNING_STATUSES and status != "cancelling":
            return {"session_id": session_id, "cancelled": False, "reason": "not_running", "status": status}
        if status in RUNNING_STATUSES:
            await self._registry.update_run_status(session_id, status="cancelling", error=None)
        await self._registry.cancel_task(session_id)
        return {"session_id": session_id, "cancelled": True}

    async def clear_run(self, session_id: str) -> dict[str, Any]:
        await self._registry.delete_run(session_id)
        return {"session_id": session_id, "cleared": True}

    async def get_status(self, session_id: str) -> dict[str, Any]:
        run = await self._registry.get_run(session_id)
        if not run:
            return {"session_id": session_id, "status": "not_found"}
        return run

    async def get_events(self, session_id: str, from_seq: int = 1, limit: int = 200) -> dict[str, Any]:
        run = await self._registry.get_run(session_id)
        if not run:
            return {"session_id": session_id, "status": "not_found", "events": [], "next_seq": from_seq}

        records = await self._registry.get_events(session_id, from_seq=from_seq, limit=limit)
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
        last_heartbeat = asyncio.get_running_loop().time()

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
                # Queue semantics: once delivered to backend stream, remove event from in-memory queue.
                await self._registry.ack_events_through(session_id, seq)
                if isinstance(payload, dict):
                    payload.clear()
                record["data"] = {}

            if status in TERMINAL_STATUSES or status == "not_found":
                return

            now = asyncio.get_running_loop().time()
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
            has_new_event = await self._registry.wait_for_events(
                session_id=session_id,
                next_seq=next_seq,
                timeout=poll_interval,
            )
            if not has_new_event:
                await asyncio.sleep(0)

    async def _run_session(self, request: RuntimeRunnerStartRequest) -> None:
        session_id = request.session_id
        await self._registry.update_run_status(
            session_id=session_id,
            status="running",
            error=None,
            set_started=True,
        )
        try:
            terminal_seen = False
            async for event, data in self._runtime_agent.run(
                session_id=request.session_id,
                agent_id=request.agent_id,
                user_id=request.user_id,
                sandbox_id=request.sandbox_id,
                user_message=request.message,
                attachments=request.attachments,
                session_status=request.session_status,
                last_plan=request.last_plan,
            ):
                await self._registry.append_event(session_id, event, data)
                if event == "error":
                    terminal_seen = True
                    await self._registry.update_run_status(
                        session_id,
                        status="failed",
                        error=str(data.get("error", "Gateway runtime error")),
                        set_finished=True,
                    )
                    return
                if event == "wait":
                    terminal_seen = True
                    await self._registry.update_run_status(
                        session_id,
                        status="waiting",
                        error=None,
                        set_finished=True,
                    )
                    return
                if event == "done":
                    terminal_seen = True
                    await self._registry.update_run_status(
                        session_id,
                        status="completed",
                        error=None,
                        set_finished=True,
                    )
                    return

            if not terminal_seen:
                error_message = "Gateway runtime stream ended without terminal event"
                await self._registry.append_event(session_id, "error", {"error": error_message})
                await self._registry.update_run_status(
                    session_id,
                    status="failed",
                    error=error_message,
                    set_finished=True,
                )
        except asyncio.CancelledError:
            await self._registry.append_event(session_id, "error", {"error": "Runner cancelled"})
            await self._registry.update_run_status(
                session_id,
                status="cancelled",
                error="Runner cancelled",
                set_finished=True,
            )
            raise
        except Exception as exc:
            await self._registry.append_event(session_id, "error", {"error": str(exc)})
            await self._registry.update_run_status(
                session_id,
                status="failed",
                error=str(exc),
                set_finished=True,
            )
        finally:
            await self._registry.attach_task(session_id, None)


runtime_runner_service = RuntimeRunnerService(runtime_service)
