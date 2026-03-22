from __future__ import annotations

import re


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def ensure_valid_session_id(session_id: str) -> str:
    if not isinstance(session_id, str):
        raise ValueError("session_id must be a string")
    value = session_id.strip()
    if not SESSION_ID_PATTERN.fullmatch(value):
        raise ValueError("invalid session_id format")
    return value

