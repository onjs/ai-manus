import sqlite3

from app.services.runtime_store import RuntimeStore


def test_runtime_store_gateway_credentials_and_runs(tmp_path):
    db_path = str(tmp_path / "runtime.db")
    store = RuntimeStore(db_path=db_path)

    store.set_gateway_credential(
        session_id="s1",
        gateway_base_url="http://gateway:8100",
        gateway_token="token",
        gateway_token_id="tid",
        gateway_token_expire_at=9999999999,
        scopes=["llm:stream"],
    )
    assert store.has_gateway_credential("s1") is True
    cred = store.get_gateway_credential("s1")
    assert cred is not None
    assert cred["gateway_token_id"] == "tid"
    assert cred["gateway_token"] == "token"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT gateway_token FROM gateway_credentials WHERE session_id = ?",
            ("s1",),
        ).fetchone()
    assert row is not None
    raw_token = str(row[0])
    assert raw_token != "token"
    assert raw_token.startswith("enc:v1:")

    run = store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="starting",
        message="hello",
        reset_events=True,
    )
    assert run["status"] == "starting"
    assert run["next_seq"] == 1

    seq1 = store.append_event("s1", "message", {"role": "assistant", "message": "a"})
    seq2 = store.append_event("s1", "done", {})
    assert seq1 == 1
    assert seq2 == 2

    events = store.get_events("s1", from_seq=1, limit=10)
    assert [e["event"] for e in events] == ["message", "done"]

    cmd_id = store.enqueue_command("s1", "start", {"session_id": "s1"})
    assert cmd_id > 0
    pending = store.get_pending_commands(limit=10)
    assert len(pending) == 1
    assert pending[0]["command_type"] == "start"

    store.mark_command_done(cmd_id)
    pending_after = store.get_pending_commands(limit=10)
    assert pending_after == []

    assert store.clear_gateway_credential("s1") is True
    assert store.has_gateway_credential("s1") is False


def test_runtime_store_purges_legacy_plaintext_gateway_tokens(tmp_path):
    db_path = str(tmp_path / "runtime_legacy.db")
    store = RuntimeStore(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO gateway_credentials(
                session_id, gateway_base_url, gateway_token, gateway_token_id,
                gateway_token_expire_at, scopes_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("legacy-s1", "http://gateway:8100", "plaintext-token", "tid", 9999999999, "[]", 1),
        )

    # Re-open store to trigger bootstrap cleanup.
    refreshed = RuntimeStore(db_path=db_path)
    assert refreshed.has_gateway_credential("legacy-s1") is False


def test_runtime_store_prunes_delivered_browser_screenshot_payload(tmp_path):
    db_path = str(tmp_path / "runtime_prune.db")
    store = RuntimeStore(db_path=db_path)

    store.upsert_run(
        session_id="s1",
        agent_id="a1",
        user_id="u1",
        status="running",
        message="hello",
        reset_events=True,
    )
    seq = store.append_event(
        "s1",
        "tool",
        {
            "type": "tool",
            "tool_name": "browser",
            "function_name": "browser_view",
            "function_args": {},
            "status": "called",
            "tool_content": {"screenshot": "data:image/png;base64,AAA"},
            "function_result": {"ok": True, "screenshot": "data:image/png;base64,BBB"},
        },
    )

    changed = store.prune_delivered_event_payload("s1", seq)
    assert changed is True

    event = store.get_events("s1", from_seq=1, limit=10)[0]
    data = event["data"]
    assert "tool_content" not in data
    assert "screenshot" not in (data.get("function_result") or {})
