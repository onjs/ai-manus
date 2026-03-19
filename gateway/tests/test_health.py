import os

from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_gateway_health_and_ready():
    os.environ["API_BASE"] = "http://mockserver:8090/v1"
    os.environ["MODEL_PROVIDER"] = "openai"
    os.environ["MODEL_NAME"] = "gpt-4o-mini"
    os.environ["GATEWAY_INTERNAL_API_KEY"] = "test-gw-key"
    os.environ["GATEWAY_REDIS_URL"] = "redis://test-redis:6379/0"
    get_settings.cache_clear()

    from app.main import app

    client = TestClient(app)

    health_resp = client.get("/v1/gateway/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["data"]["status"] == "ok"

    ready_resp = client.get("/v1/gateway/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["data"]["ready"] is True

    hash_resp = client.get("/v1/gateway/config/hash")
    assert hash_resp.status_code == 200
    assert "route_hash" in hash_resp.json()["data"]
