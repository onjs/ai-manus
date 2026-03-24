from typing import Any, Optional, AsyncGenerator, List
import logging
import re
from datetime import datetime
from app.domain.models.session import Session, SessionStatus
from app.domain.external.sandbox import Sandbox
from app.domain.models.event import BaseEvent, ErrorEvent, DoneEvent, MessageEvent, WaitEvent, AgentEvent
from pydantic import TypeAdapter
from app.domain.repositories.session_repository import SessionRepository
from app.domain.external.task import Task
from typing import Type
from app.domain.external.file import FileStorage
from app.domain.models.file import FileInfo
from app.domain.services.runtime.base import AgentRuntime
from app.domain.services.runtime.factory import AgentRuntimeFactory
from app.domain.services.chat_idempotency_service import ChatIdempotencyService
from app.infrastructure.external.gateway.client import GatewayClient

# Setup logging
logger = logging.getLogger(__name__)

class AgentDomainService:
    """
    Agent domain service, responsible for coordinating the work of planning agent and execution agent
    """
    
    _STREAM_ID_PATTERN = re.compile(r"^\d+-\d+$")

    def __init__(
        self,
        session_repository: SessionRepository,
        sandbox_cls: Type[Sandbox],
        task_cls: Type[Task],
        file_storage: FileStorage,
        gateway_client: Optional[GatewayClient] = None,
    ):
        self._session_repository = session_repository
        self._task_cls = task_cls
        self._chat_idempotency = ChatIdempotencyService()
        self._runtime: AgentRuntime = AgentRuntimeFactory(
            task_cls=task_cls,
            sandbox_cls=sandbox_cls,
            session_repository=session_repository,
            file_storage=file_storage,
            gateway_client=gateway_client,
        ).create()
        logger.info("AgentDomainService initialization completed")
            
    async def shutdown(self) -> None:
        """Clean up all Agent's resources"""
        logger.info("Starting to close all Agents")
        await self._task_cls.destroy()
        logger.info("All agents closed successfully")

    async def _create_task(self, session: Session) -> Task:
        """Create a new agent task"""
        return await self._runtime.create_task(session)
        
    async def _get_task(self, session: Session) -> Optional[Task]:
        """Get a task for the given session"""

        task_id = session.task_id
        if not task_id:
            return None
        
        return self._task_cls.get(task_id)

    async def stop_session(self, session_id: str) -> None:
        """Stop a session"""
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to stop non-existent Session {session_id}")
            raise RuntimeError("Session not found")
        task = await self._get_task(session)
        if task:
            task.cancel()
        await self._session_repository.update_status(session_id, SessionStatus.COMPLETED)

    @classmethod
    def _is_stream_id(cls, value: Optional[str]) -> bool:
        if not value:
            return False
        return bool(cls._STREAM_ID_PATTERN.match(value.strip()))

    def _validate_cursor(self, latest_event_id: Optional[str]) -> Optional[str]:
        if not latest_event_id:
            return None
        cursor = latest_event_id.strip()
        if not self._is_stream_id(cursor):
            raise RuntimeError("event_id must be a valid stream id")
        return cursor

    async def _resolve_stream_start_id(self, task: Task, cursor_event_id: Optional[str], has_new_message: bool) -> str:
        if cursor_event_id:
            return cursor_event_id
        if not has_new_message:
            return "0"
        get_latest_id = getattr(task.output_stream, "get_latest_id", None)
        if not callable(get_latest_id):
            raise RuntimeError("output stream does not support get_latest_id")
        latest_id = await get_latest_id()
        if not isinstance(latest_id, str) or not latest_id:
            raise RuntimeError("output stream returned invalid latest id")
        return latest_id

    async def _replay_cached_events(self, payloads: list[dict[str, Any]]) -> AsyncGenerator[BaseEvent, None]:
        for payload in payloads:
            yield TypeAdapter(AgentEvent).validate_python(payload)

    async def chat(
        self,
        session_id: str,
        user_id: str,
        message: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        latest_event_id: Optional[str] = None,
        request_id: Optional[str] = None,
        attachments: Optional[List[dict]] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Chat with an agent
        """

        replay_request_id: Optional[str] = None
        replay_events: list[dict[str, Any]] = []
        replay_terminal = False
        idempotency_lock_acquired = False
        session: Optional[Session] = None
        try:
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
            if not session:
                logger.error(f"Attempted to chat with non-existent Session {session_id} for user {user_id}")
                raise RuntimeError("Session not found")

            task = await self._get_task(session)
            has_message = bool(message and message.strip())
            cursor_event_id = self._validate_cursor(latest_event_id)
            replay_request_id = request_id.strip() if request_id else None
            if has_message and not replay_request_id:
                raise RuntimeError("request_id is required when message is provided")
            if not has_message:
                replay_request_id = None

            if replay_request_id:
                snapshot = await self._chat_idempotency.get_snapshot(session_id, replay_request_id)
                if snapshot:
                    if snapshot.status != "completed":
                        raise RuntimeError("duplicate request is still running")
                    async for replay_event in self._replay_cached_events(snapshot.events):
                        yield replay_event
                    return
                started = await self._chat_idempotency.try_start(session_id, replay_request_id)
                if not started:
                    raise RuntimeError("duplicate request is still running")
                idempotency_lock_acquired = True

            if has_message:
                if session.status != SessionStatus.RUNNING or task is None:
                    task = await self._create_task(session)
                    if not task:
                        raise RuntimeError("Failed to create task")
                
                await self._session_repository.update_latest_message(session_id, message, timestamp or datetime.now())
                cursor_event_id = await self._resolve_stream_start_id(task, cursor_event_id, has_new_message=True)

                message_event = MessageEvent(
                    message=message, 
                    role="user", 
                    attachments=[
                        FileInfo(file_id=attachment["file_id"], filename=attachment["filename"])
                        for attachment in attachments
                    ] if attachments else None
                )

                event_id = await task.input_stream.put(message_event.model_dump_json())

                message_event.id = event_id
                await self._session_repository.add_event(session_id, message_event)
                
                await task.run()
                logger.debug("Put message into Session %s input queue", session_id)
            elif task:
                cursor_event_id = await self._resolve_stream_start_id(task, cursor_event_id, has_new_message=False)
            
            logger.info(f"Session {session_id} started")
            logger.debug("Session %s task: %s", session_id, task)
           
            while task:
                event_id, event_str = await task.output_stream.get(start_id=cursor_event_id, block_ms=200)
                cursor_event_id = event_id
                if event_str is None:
                    if task.done:
                        break
                    logger.debug(f"No event found in Session {session_id}'s event queue")
                    continue
                event = TypeAdapter(AgentEvent).validate_json(event_str)
                event.id = event_id
                logger.debug("Got event from Session %s output queue: %s", session_id, type(event).__name__)
                await self._session_repository.update_unread_message_count(session_id, 0)
                if replay_request_id:
                    replay_events.append(event.model_dump(mode="json"))
                yield event
                if isinstance(event, (DoneEvent, ErrorEvent, WaitEvent)):
                    replay_terminal = True
                    break
            
            logger.info(f"Session {session_id} completed")

        except Exception as e:
            logger.exception(f"Error in Session {session_id}")
            event = ErrorEvent(error=str(e))
            if session is not None:
                await self._session_repository.add_event(session_id, event)
            if replay_request_id:
                replay_events.append(event.model_dump(mode="json"))
                replay_terminal = True
            yield event # TODO: raise api exception
        finally:
            if replay_request_id and idempotency_lock_acquired:
                if replay_events and replay_terminal:
                    await self._chat_idempotency.mark_completed(session_id, replay_request_id, replay_events)
                else:
                    await self._chat_idempotency.clear(session_id, replay_request_id)
            if session is not None:
                await self._session_repository.update_unread_message_count(session_id, 0)
