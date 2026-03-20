import pytest
import sqlite3

from app.schemas.runtime import RuntimeGatewayConfigRequest
from app.services.runtime import RuntimeService


@pytest.mark.asyncio
async def test_runtime_service_configure_and_clear(tmp_path):
    service = RuntimeService()
    service._store = service._store.__class__(db_path=str(tmp_path / "runtime_service_1.db"))  # noqa: SLF001
    req = RuntimeGatewayConfigRequest(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )
    configured = await service.configure_gateway(req)
    assert configured["configured"] is True
    assert service.has_gateway_config("s1") is True

    cleared = await service.clear_gateway("s1")
    assert cleared["cleared"] is True
    assert service.has_gateway_config("s1") is False


@pytest.mark.asyncio
async def test_runtime_service_get_chat_model_kwargs_requires_config(tmp_path):
    service = RuntimeService()
    service._store = service._store.__class__(db_path=str(tmp_path / "runtime_service_2.db"))  # noqa: SLF001

    with pytest.raises(RuntimeError, match="Gateway runtime is not configured"):
        service.get_chat_model_kwargs("missing")


@pytest.mark.asyncio
async def test_runtime_service_get_chat_model_kwargs_rejects_expired_token(tmp_path):
    service = RuntimeService()
    service._store = service._store.__class__(db_path=str(tmp_path / "runtime_service_3.db"))  # noqa: SLF001
    conf = RuntimeGatewayConfigRequest(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=1,
        scopes=["llm:stream"],
    )
    await service.configure_gateway(conf)

    with pytest.raises(RuntimeError, match="Gateway token expired"):
        service.get_chat_model_kwargs("s1")


@pytest.mark.asyncio
async def test_runtime_service_get_chat_model_kwargs_rejects_invalid_credential_and_clears(tmp_path):
    db_path = str(tmp_path / "runtime_service_4.db")
    service = RuntimeService()
    service._store = service._store.__class__(db_path=db_path)  # noqa: SLF001

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO gateway_credentials(
                session_id, gateway_base_url, gateway_token, gateway_token_id,
                gateway_token_expire_at, scopes_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("s1", "http://gateway:8100", "enc:v1:broken-token", "tid", 9999999999, "[]", 1),
        )

    with pytest.raises(RuntimeError, match="Gateway credential is invalid"):
        service.get_chat_model_kwargs("s1")

    assert service.has_gateway_config("s1") is False
