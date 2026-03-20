import asyncio
import logging
from typing import Any

from app.services.runtime_agent import RuntimeAgentService
from app.services.runtime import RuntimeService, runtime_service
from app.services.runtime_store import RuntimeStore, runtime_store

logger = logging.getLogger(__name__)


class RuntimeRunnerDaemon:
    """Dedicated sandbox runner process managed by supervisor."""

    def __init__(self, store: RuntimeStore, gateway_runtime: RuntimeService, runtime_agent: RuntimeAgentService):
        self._store = store
        self._gateway_runtime = gateway_runtime
        self._runtime_agent = runtime_agent
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        logger.info("Runtime runner daemon started")
        while not self._stop_event.is_set():
            await self._process_pending_commands()
            await asyncio.sleep(0.2)

    async def stop(self) -> None:
        self._stop_event.set()
        tasks = list(self._active_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_pending_commands(self) -> None:
        commands = self._store.get_pending_commands(limit=100)
        for command in commands:
            cid = int(command["id"])
            try:
                await self._handle_command(command)
                self._store.mark_command_done(cid)
            except Exception as e:
                logger.exception("Runner command failed: id=%s type=%s", cid, command.get("command_type"))
                self._store.mark_command_failed(cid, str(e))

    async def _handle_command(self, command: dict[str, Any]) -> None:
        command_type = str(command.get("command_type"))
        payload = command.get("payload") or {}
        session_id = str(command.get("session_id"))

        if command_type == "start":
            await self._start_run(payload, session_id)
            return
        if command_type == "cancel":
            await self._cancel_run(session_id)
            return
        if command_type == "clear":
            await self._clear_run(session_id)
            return

        raise ValueError(f"Unsupported command_type: {command_type}")

    async def _start_run(self, payload: dict[str, Any], session_id: str) -> None:
        existing_task = self._active_tasks.get(session_id)
        if existing_task and not existing_task.done():
            return

        agent_id = str(payload.get("agent_id") or "")
        user_id = str(payload.get("user_id") or "")
        sandbox_id = str(payload.get("sandbox_id") or "")
        message = str(payload.get("message") or "")
        run = self._store.get_run(session_id)
        if not run:
            self._store.upsert_run(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                status="starting",
                message=message,
                error=None,
                reset_events=True,
            )

        task = asyncio.create_task(self._run_session(session_id, agent_id, user_id, sandbox_id, message))
        self._active_tasks[session_id] = task

    async def _cancel_run(self, session_id: str) -> None:
        task = self._active_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            return
        run = self._store.get_run(session_id)
        if not run:
            return
        status = str(run.get("status") or "")
        if status in {"starting", "running", "cancelling"}:
            self._store.update_run_status(session_id, status="cancelled", error="Runner cancelled", set_finished=True)

    async def _clear_run(self, session_id: str) -> None:
        task = self._active_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
        self._active_tasks.pop(session_id, None)
        self._store.delete_run(session_id)

    async def _run_session(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        sandbox_id: str,
        message: str,
    ) -> None:
        self._store.update_run_status(session_id, status="running", error=None, set_started=True)

        try:
            terminal_seen = False
            async for event, data in self._runtime_agent.run(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                sandbox_id=sandbox_id,
                user_message=message,
            ):
                self._store.append_event(session_id, event, data)
                if event == "error":
                    terminal_seen = True
                    self._store.update_run_status(
                        session_id,
                        status="failed",
                        error=str(data.get("error", "Gateway runtime error")),
                        set_finished=True,
                    )
                    return
                if event == "wait":
                    terminal_seen = True
                    self._store.update_run_status(
                        session_id,
                        status="waiting",
                        error=None,
                        set_finished=True,
                    )
                    return
                if event == "done":
                    terminal_seen = True
                    self._store.update_run_status(session_id, status="completed", error=None, set_finished=True)
                    return

            if not terminal_seen:
                error_message = "Gateway runtime stream ended without terminal event"
                self._store.append_event(session_id, "error", {"error": error_message})
                self._store.update_run_status(session_id, status="failed", error=error_message, set_finished=True)
        except asyncio.CancelledError:
            self._store.append_event(session_id, "error", {"error": "Runner cancelled"})
            self._store.update_run_status(session_id, status="cancelled", error="Runner cancelled", set_finished=True)
            raise
        except Exception as e:
            logger.exception("Runner execution failed: session_id=%s", session_id)
            self._store.append_event(session_id, "error", {"error": str(e)})
            self._store.update_run_status(session_id, status="failed", error=str(e), set_finished=True)
        finally:
            self._active_tasks.pop(session_id, None)


runtime_runner_daemon = RuntimeRunnerDaemon(
    runtime_store,
    runtime_service,
    RuntimeAgentService(runtime_service),
)
