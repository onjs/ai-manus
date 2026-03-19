#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


TERMINAL_EVENTS = {"done", "wait", "error"}


@dataclass
class RunSummary:
    session_id: str
    seen_events: set[str]
    terminal_event: str | None
    event_count: int


def _parse_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _validate_event_payload(event_name: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"{event_name}: payload must be an object")
    if "timestamp" not in payload:
        raise ValueError(f"{event_name}: missing timestamp")

    if event_name == "tool":
        for key in ("name", "function", "args", "status"):
            if key not in payload:
                raise ValueError(f"tool: missing {key}")
    elif event_name == "step":
        for key in ("id", "description", "status"):
            if key not in payload:
                raise ValueError(f"step: missing {key}")
    elif event_name == "message":
        for key in ("role", "content"):
            if key not in payload:
                raise ValueError(f"message: missing {key}")
    elif event_name == "error":
        if "error" not in payload:
            raise ValueError("error: missing error")


def _assert_contains(seen: set[str], expected: list[str], label: str) -> None:
    missing = [event for event in expected if event not in seen]
    if missing:
        raise RuntimeError(f"missing {label} events: {', '.join(missing)}")


async def _login_if_needed(
    client: httpx.AsyncClient,
    base_url: str,
    bearer_token: str | None,
    email: str | None,
    password: str | None,
) -> str | None:
    if bearer_token:
        return bearer_token

    status_resp = await client.get(f"{base_url}/auth/status")
    status_resp.raise_for_status()
    provider = status_resp.json().get("data", {}).get("auth_provider")
    if provider == "none":
        return None

    if not email or not password:
        raise RuntimeError("auth is enabled: set E2E_EMAIL and E2E_PASSWORD (or E2E_BEARER_TOKEN)")

    login_resp = await client.post(
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
    )
    login_resp.raise_for_status()
    token = login_resp.json().get("data", {}).get("access_token")
    if not token:
        raise RuntimeError("login succeeded but access_token is missing")
    return token


async def _create_session(client: httpx.AsyncClient, base_url: str, headers: dict[str, str]) -> str:
    resp = await client.put(f"{base_url}/sessions", headers=headers)
    resp.raise_for_status()
    session_id = resp.json().get("data", {}).get("session_id")
    if not session_id:
        raise RuntimeError("create session response missing session_id")
    return str(session_id)


async def _stream_chat(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    session_id: str,
    message: str,
    timeout_seconds: int,
) -> RunSummary:
    payload = {
        "message": message,
        "timestamp": int(time.time()),
        "request_id": f"e2e-{uuid.uuid4().hex[:12]}",
        "attachments": [],
    }
    seen_events: set[str] = set()
    terminal_event: str | None = None
    event_count = 0

    event_name: str | None = None
    data_lines: list[str] = []
    started = time.time()

    async with client.stream(
        "POST",
        f"{base_url}/sessions/{session_id}/chat",
        headers=headers,
        json=payload,
        timeout=timeout_seconds + 5,
    ) as response:
        response.raise_for_status()

        async for raw_line in response.aiter_lines():
            if time.time() - started > timeout_seconds:
                raise TimeoutError(f"chat stream timeout after {timeout_seconds}s")

            line = raw_line.strip()
            if not line:
                if event_name or data_lines:
                    current_event = event_name or "message"
                    raw_data = "\n".join(data_lines).strip()
                    event_payload = json.loads(raw_data) if raw_data else {}
                    _validate_event_payload(current_event, event_payload)
                    seen_events.add(current_event)
                    event_count += 1
                    if current_event in TERMINAL_EVENTS:
                        terminal_event = current_event
                        break
                event_name = None
                data_lines = []
                continue

            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())

    return RunSummary(
        session_id=session_id,
        seen_events=seen_events,
        terminal_event=terminal_event,
        event_count=event_count,
    )


async def _verify_session_events(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    session_id: str,
) -> set[str]:
    resp = await client.get(f"{base_url}/sessions/{session_id}", headers=headers)
    resp.raise_for_status()
    events = resp.json().get("data", {}).get("events", [])
    seen: set[str] = set()
    for event in events:
        event_name = event.get("event")
        payload = event.get("data") or {}
        if not isinstance(event_name, str):
            continue
        _validate_event_payload(event_name, payload)
        seen.add(event_name)
    return seen


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backend->Frontend SSE contract regression")
    parser.add_argument("--base-url", default=os.getenv("E2E_BASE_URL", "http://localhost:8000/api/v1"))
    parser.add_argument("--message", default=os.getenv("E2E_MESSAGE", "请打开浏览器并进入一个网页，然后返回总结。"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.getenv("E2E_TIMEOUT_SECONDS", "180")))
    parser.add_argument("--require-events", default=os.getenv("E2E_REQUIRE_EVENTS", "tool,step,message"))
    parser.add_argument("--require-terminal", default=os.getenv("E2E_REQUIRE_TERMINAL", "done,wait,error"))
    parser.add_argument("--bearer-token", default=os.getenv("E2E_BEARER_TOKEN"))
    parser.add_argument("--email", default=os.getenv("E2E_EMAIL"))
    parser.add_argument("--password", default=os.getenv("E2E_PASSWORD"))
    args = parser.parse_args()

    required_events = _parse_list(args.require_events)
    required_terminal = _parse_list(args.require_terminal)

    async with httpx.AsyncClient() as client:
        token = await _login_if_needed(
            client=client,
            base_url=args.base_url.rstrip("/"),
            bearer_token=args.bearer_token,
            email=args.email,
            password=args.password,
        )
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        session_id = await _create_session(client, args.base_url.rstrip("/"), headers)
        summary = await _stream_chat(
            client=client,
            base_url=args.base_url.rstrip("/"),
            headers=headers,
            session_id=session_id,
            message=args.message,
            timeout_seconds=args.timeout_seconds,
        )
        _assert_contains(summary.seen_events, required_events, "stream")

        if summary.terminal_event is None:
            raise RuntimeError("stream ended without terminal event")
        if summary.terminal_event not in required_terminal:
            raise RuntimeError(
                f"unexpected terminal event: {summary.terminal_event}, allowed: {', '.join(required_terminal)}"
            )

        persisted_seen = await _verify_session_events(
            client=client,
            base_url=args.base_url.rstrip("/"),
            headers=headers,
            session_id=summary.session_id,
        )
        _assert_contains(persisted_seen, required_events, "persisted session")

    print(
        json.dumps(
            {
                "session_id": summary.session_id,
                "event_count": summary.event_count,
                "stream_seen": sorted(summary.seen_events),
                "terminal_event": summary.terminal_event,
                "persisted_seen": sorted(persisted_seen),
                "result": "ok",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"result": "failed", "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
