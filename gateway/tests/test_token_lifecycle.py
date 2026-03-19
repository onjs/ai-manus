import os
import time
from typing import Any, AsyncGenerator

from fastapi.testclient import TestClient

from app.application.services.token_service import TokenService
from app.core.auth import get_token_service
from app.core.config import get_settings


class FakeProvider:
    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_message = payload["messages"][-1]["content"]
        return {
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"ok:{user_message}"}}],
        }

    async def stream_chat_completion(self, payload: dict[str, Any]) -> AsyncGenerator[bytes, None]:
        user_message = payload["messages"][-1]["content"]
        yield (
            f'data: {{"id":"chatcmpl_test","choices":[{{"index":0,"delta":{{"content":"ok:{user_message}"}}}}]}}\\n\\n'
        ).encode("utf-8")
        yield b"data: [DONE]\n\n"


class InMemoryTokenStateRepository:
    def __init__(self) -> None:
        self._active: dict[str, tuple[dict[str, Any], int]] = {}
        self._revoked: dict[str, tuple[dict[str, Any], int]] = {}

    async def set_active(self, token_id: str, claims: dict[str, Any], ttl_seconds: int) -> None:
        self._active[token_id] = (claims, int(time.time()) + max(1, ttl_seconds))

    async def get_active(self, token_id: str) -> dict[str, Any] | None:
        item = self._active.get(token_id)
        if item is None:
            return None
        payload, expire_at = item
        if expire_at <= int(time.time()):
            self._active.pop(token_id, None)
            return None
        return payload

    async def remove_active(self, token_id: str) -> None:
        self._active.pop(token_id, None)

    async def set_revoked(self, token_id: str, reason: str, ttl_seconds: int) -> None:
        self._revoked[token_id] = (
            {"reason": reason, "revoked_at": int(time.time())},
            int(time.time()) + max(1, ttl_seconds),
        )

    async def get_revoked(self, token_id: str) -> dict[str, Any] | None:
        item = self._revoked.get(token_id)
        if item is None:
            return None
        payload, expire_at = item
        if expire_at <= int(time.time()):
            self._revoked.pop(token_id, None)
            return None
        return payload


def _prepare_env() -> None:
    os.environ["API_BASE"] = "http://mockserver:8090/v1"
    os.environ["MODEL_PROVIDER"] = "openai"
    os.environ["MODEL_NAME"] = "gpt-4o-mini"
    os.environ["GATEWAY_INTERNAL_API_KEY"] = "internal-key"
    os.environ["GATEWAY_TOKEN_ISSUER_SECRET"] = "secret-key-secret-key-secret-key-32"
    os.environ["GATEWAY_REDIS_URL"] = "redis://test-redis:6379/0"
    get_settings.cache_clear()
    get_token_service.cache_clear()


def _override_token_service(app: Any) -> None:
    token_service = TokenService(
        settings=get_settings(),
        state_repository=InMemoryTokenStateRepository(),
    )
    app.dependency_overrides[get_token_service] = lambda: token_service


def test_token_issue_scope_stream_revoke(monkeypatch):
    _prepare_env()
    from app.interfaces.api import runtime_routes
    from app.main import app

    monkeypatch.setattr(runtime_routes.ProviderFactory, "create", lambda settings: FakeProvider())
    app.dependency_overrides.clear()
    _override_token_service(app)
    client = TestClient(app)

    issue_payload = {
        "tenant_id": "t1",
        "session_id": "s1",
        "env_id": "e1",
        "run_id": "r1",
        "agent_id": "a1",
        "scopes": ["llm:stream"],
    }
    issue_resp = client.post(
        "/v1/token/issue",
        json=issue_payload,
        headers={"X-Internal-Key": "internal-key"},
    )
    assert issue_resp.status_code == 200
    token = issue_resp.json()["data"]["token"]
    token_id = issue_resp.json()["data"]["token_id"]

    stream_payload = {
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    }
    stream_resp = client.post(
        "/v1/chat/completions",
        json=stream_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stream_resp.status_code == 200
    assert "data: {\"id\":\"chatcmpl_test\"" in stream_resp.text

    revoke_resp = client.post(
        "/v1/token/revoke",
        json={"token_id": token_id, "reason": "done"},
        headers={"X-Internal-Key": "internal-key"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["data"]["revoked"] is True

    introspect_resp = client.post(
        "/v1/token/introspect",
        json={"token": token},
        headers={"X-Internal-Key": "internal-key"},
    )
    assert introspect_resp.status_code == 200
    assert introspect_resp.json()["data"]["active"] is False
    assert introspect_resp.json()["data"]["revoked"] is True

    stream_after_revoke = client.post(
        "/v1/chat/completions",
        json=stream_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stream_after_revoke.status_code == 401


def test_scope_denied(monkeypatch):
    _prepare_env()
    from app.interfaces.api import runtime_routes
    from app.main import app

    monkeypatch.setattr(runtime_routes.ProviderFactory, "create", lambda settings: FakeProvider())
    app.dependency_overrides.clear()
    _override_token_service(app)
    client = TestClient(app)

    issue_resp = client.post(
        "/v1/token/issue",
        json={
            "tenant_id": "t1",
            "session_id": "s1",
            "env_id": "e1",
            "run_id": "r1",
            "agent_id": "a1",
            "scopes": ["llm:ask"],
        },
        headers={"X-Internal-Key": "internal-key"},
    )
    token = issue_resp.json()["data"]["token"]

    stream_resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stream_resp.status_code == 403
