import json
import time
from typing import Any, Optional

from redis.asyncio import Redis


class TokenStateRepository:
    """Token state storage backed by Redis."""

    def __init__(self, redis_url: str, key_prefix: str = "gw"):
        if not redis_url or not redis_url.strip():
            raise ValueError("redis_url is required")
        self._redis: Redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix

    def _active_key(self, token_id: str) -> str:
        return f"{self._prefix}:token:active:{token_id}"

    def _revoked_key(self, token_id: str) -> str:
        return f"{self._prefix}:token:revoked:{token_id}"

    async def set_active(self, token_id: str, claims: dict[str, Any], ttl_seconds: int) -> None:
        ttl = max(1, ttl_seconds)
        await self._redis.setex(self._active_key(token_id), ttl, json.dumps(claims, ensure_ascii=False))

    async def get_active(self, token_id: str) -> Optional[dict[str, Any]]:
        value = await self._redis.get(self._active_key(token_id))
        if value is None:
            return None
        return json.loads(value)

    async def remove_active(self, token_id: str) -> None:
        await self._redis.delete(self._active_key(token_id))

    async def set_revoked(self, token_id: str, reason: str, ttl_seconds: int) -> None:
        payload = {"reason": reason, "revoked_at": int(time.time())}
        ttl = max(1, ttl_seconds)
        await self._redis.setex(self._revoked_key(token_id), ttl, json.dumps(payload, ensure_ascii=False))

    async def get_revoked(self, token_id: str) -> Optional[dict[str, Any]]:
        value = await self._redis.get(self._revoked_key(token_id))
        if value is None:
            return None
        return json.loads(value)
