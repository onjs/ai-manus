import os
from typing import Any, AsyncGenerator

from fastapi.testclient import TestClient

from app.core.auth import get_token_service
from app.core.config import get_settings


class FakeProvider:
    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_message = payload["messages"][-1]["content"]
        return {
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"echo:{user_message}"}}],
        }

    async def stream_chat_completion(self, payload: dict[str, Any]) -> AsyncGenerator[bytes, None]:
        user_message = payload["messages"][-1]["content"]
        yield (
            f'data: {{"id":"chatcmpl_test","choices":[{{"index":0,"delta":{{"content":"echo:{user_message}"}}}}]}}\\n\\n'
        ).encode("utf-8")
        yield b"data: [DONE]\n\n"


def _prepare_env() -> None:
    os.environ["API_BASE"] = "http://mockserver:8090/v1"
    os.environ["MODEL_PROVIDER"] = "openai"
    os.environ["MODEL_NAME"] = "gpt-4o-mini"
    os.environ["GATEWAY_INTERNAL_API_KEY"] = "test-gw-key"
    os.environ["GATEWAY_TOKEN_ISSUER_SECRET"] = "secret-key-secret-key-secret-key-32"
    os.environ["GATEWAY_REDIS_URL"] = ""
    get_settings.cache_clear()
    get_token_service.cache_clear()


def _issue_token(client: TestClient, scopes: list[str]) -> str:
    issue = client.post(
        "/v1/token/issue",
        json={
            "tenant_id": "t1",
            "session_id": "s1",
            "env_id": "e1",
            "run_id": "r1",
            "agent_id": "a1",
            "scopes": scopes,
        },
        headers={"X-Internal-Key": "test-gw-key"},
    )
    assert issue.status_code == 200
    return issue.json()["data"]["token"]


def test_chat_completions_requires_bearer_token(monkeypatch):
    _prepare_env()
    from app.interfaces.api import runtime_routes
    from app.main import app

    monkeypatch.setattr(runtime_routes.ProviderFactory, "create", lambda settings: FakeProvider())

    client = TestClient(app)
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 401


def test_chat_completions_non_stream(monkeypatch):
    _prepare_env()
    from app.interfaces.api import runtime_routes
    from app.main import app

    monkeypatch.setattr(runtime_routes.ProviderFactory, "create", lambda settings: FakeProvider())

    client = TestClient(app)
    token = _issue_token(client, ["llm:stream"])
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "echo:hello"


def test_chat_completions_stream(monkeypatch):
    _prepare_env()
    from app.interfaces.api import runtime_routes
    from app.main import app

    monkeypatch.setattr(runtime_routes.ProviderFactory, "create", lambda settings: FakeProvider())

    client = TestClient(app)
    token = _issue_token(client, ["llm:stream"])
    payload = {"messages": [{"role": "user", "content": "hello"}], "stream": True}
    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.text
    assert "data: {\"id\":\"chatcmpl_test\"" in body
    assert "echo:hello" in body
    assert "data: [DONE]" in body


def test_chat_completions_scope_denied(monkeypatch):
    _prepare_env()
    from app.interfaces.api import runtime_routes
    from app.main import app

    monkeypatch.setattr(runtime_routes.ProviderFactory, "create", lambda settings: FakeProvider())

    client = TestClient(app)
    token = _issue_token(client, ["llm:ask"])
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
