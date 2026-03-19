import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.infrastructure.storage.redis import RedisClient, get_redis


@dataclass
class ReplaySnapshot:
    status: str
    events: list[dict[str, Any]]


class ChatIdempotencyService:
    """Store/replay chat results keyed by (session_id, request_id)."""

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        key_prefix: str = "chat:idempotency",
        running_ttl_seconds: int = 300,
        completed_ttl_seconds: int = 24 * 60 * 60,
    ) -> None:
        self._redis = redis_client or get_redis()
        self._key_prefix = key_prefix
        self._running_ttl_seconds = running_ttl_seconds
        self._completed_ttl_seconds = completed_ttl_seconds

    def _key(self, session_id: str, request_id: str) -> str:
        return f"{self._key_prefix}:{session_id}:{request_id}"

    async def get_snapshot(self, session_id: str, request_id: str) -> Optional[ReplaySnapshot]:
        payload = await self._redis.client.get(self._key(session_id, request_id))
        if not payload:
            return None
        try:
            data = json.loads(payload)
            return ReplaySnapshot(
                status=str(data.get("status", "unknown")),
                events=list(data.get("events") or []),
            )
        except Exception:
            return None

    async def try_start(self, session_id: str, request_id: str) -> bool:
        payload = json.dumps(
            {
                "status": "running",
                "events": [],
                "updated_at": int(time.time()),
            },
            ensure_ascii=False,
        )
        result = await self._redis.client.set(
            self._key(session_id, request_id),
            payload,
            ex=self._running_ttl_seconds,
            nx=True,
        )
        return bool(result)

    async def mark_completed(
        self,
        session_id: str,
        request_id: str,
        events: list[dict[str, Any]],
    ) -> None:
        payload = json.dumps(
            {
                "status": "completed",
                "events": events,
                "updated_at": int(time.time()),
            },
            ensure_ascii=False,
        )
        await self._redis.client.set(
            self._key(session_id, request_id),
            payload,
            ex=self._completed_ttl_seconds,
        )

    async def clear(self, session_id: str, request_id: str) -> None:
        await self._redis.client.delete(self._key(session_id, request_id))
