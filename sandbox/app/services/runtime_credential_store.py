from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.runtime_session_id import ensure_valid_session_id

class RuntimeCredentialStore:
    """Session-scoped gateway credential store backed by temp files."""

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is None:
            base_dir = settings.RUNTIME_GATEWAY_CREDENTIAL_DIR
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _credential_path(self, session_id: str) -> Path:
        safe_session_id = ensure_valid_session_id(session_id)
        return self._base_dir / f"{safe_session_id}.json"

    def set_gateway_credential(
        self,
        session_id: str,
        gateway_base_url: str,
        gateway_token: str,
        gateway_token_id: str,
        gateway_token_expire_at: int,
        scopes: list[str],
    ) -> None:
        path = self._credential_path(session_id)
        payload = {
            "session_id": session_id,
            "gateway_base_url": gateway_base_url,
            "gateway_token": gateway_token,
            "gateway_token_id": gateway_token_id,
            "gateway_token_expire_at": int(gateway_token_expire_at),
            "scopes": list(scopes),
            "updated_at": int(time.time()),
        }
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.chmod(0o600)
        temp_path.replace(path)

    def clear_gateway_credential(self, session_id: str) -> bool:
        path = self._credential_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def has_gateway_credential(self, session_id: str) -> bool:
        return self._credential_path(session_id).exists()

    def get_gateway_credential(self, session_id: str) -> dict[str, Any] | None:
        path = self._credential_path(session_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Gateway credential payload must be an object")
        return payload


runtime_credential_store = RuntimeCredentialStore()
