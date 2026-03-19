import json
import time
from typing import Any, Optional

from redis.asyncio import Redis


class TokenStateRepository:
    """Token state storage with Redis-first and in-memory fallback."""

    def __init__(self, redis_url: Optional[str], key_prefix: str = "gw"):
        self._redis: Optional[Redis] = Redis.from_url(redis_url) if redis_url else None
        self._prefix = key_prefix
        self._active_mem: dict[str, tuple[dict[str, Any], float]] = {}
        self._revoked_mem: dict[str, tuple[dict[str, Any], float]] = {}

    def _active_key(self, token_id: str) -> str:
        return f"{self._prefix}:token:active:{token_id}"

    def _revoked_key(self, token_id: str) -> str:
        return f"{self._prefix}:token:revoked:{token_id}"

    async def set_active(self, token_id: str, claims: dict[str, Any], ttl_seconds: int) -> None:
        ttl = max(1, ttl_seconds)
        if self._redis:
            try:
                await self._redis.setex(self._active_key(token_id), ttl, json.dumps(claims, ensure_ascii=False))
                return
            except Exception:
                pass
        self._active_mem[token_id] = (claims, time.time() + ttl)

    async def get_active(self, token_id: str) -> Optional[dict[str, Any]]:
        if self._redis:
            try:
                value = await self._redis.get(self._active_key(token_id))
                if value is None:
                    return None
                return json.loads(value)
            except Exception:
                pass
        entry = self._active_mem.get(token_id)
        if not entry:
            return None
        payload, expire_at = entry
        if expire_at <= time.time():
            self._active_mem.pop(token_id, None)
            return None
        return payload

    async def remove_active(self, token_id: str) -> None:
        if self._redis:
            try:
                await self._redis.delete(self._active_key(token_id))
                return
            except Exception:
                pass
        self._active_mem.pop(token_id, None)

    async def set_revoked(self, token_id: str, reason: str, ttl_seconds: int) -> None:
        payload = {"reason": reason, "revoked_at": int(time.time())}
        ttl = max(1, ttl_seconds)
        if self._redis:
            try:
                await self._redis.setex(self._revoked_key(token_id), ttl, json.dumps(payload, ensure_ascii=False))
                return
            except Exception:
                pass
        self._revoked_mem[token_id] = (payload, time.time() + ttl)

    async def get_revoked(self, token_id: str) -> Optional[dict[str, Any]]:
        if self._redis:
            try:
                value = await self._redis.get(self._revoked_key(token_id))
                if value is None:
                    return None
                return json.loads(value)
            except Exception:
                pass
        entry = self._revoked_mem.get(token_id)
        if not entry:
            return None
        payload, expire_at = entry
        if expire_at <= time.time():
            self._revoked_mem.pop(token_id, None)
            return None
        return payload
