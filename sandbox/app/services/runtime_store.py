import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.services.secret_cipher import SecretCipher


class RuntimeStore:
    """SQLite-backed shared store for runtime runner/API processes."""

    def __init__(self, db_path: str | None = None, secret_cipher: SecretCipher | None = None):
        self._db_path = db_path or settings.RUNTIME_DB_PATH
        self._secret_cipher = secret_cipher or SecretCipher(settings.SANDBOX_INTERNAL_API_KEY or "")
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_credentials (
                    session_id TEXT PRIMARY KEY,
                    gateway_base_url TEXT NOT NULL,
                    gateway_token TEXT NOT NULL,
                    gateway_token_id TEXT NOT NULL,
                    gateway_token_expire_at INTEGER NOT NULL,
                    scopes_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    session_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    error TEXT,
                    created_at INTEGER NOT NULL,
                    started_at INTEGER,
                    finished_at INTEGER,
                    last_heartbeat_at INTEGER NOT NULL,
                    next_seq INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    UNIQUE(session_id, seq)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    command_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at INTEGER NOT NULL,
                    processed_at INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_session_seq ON events(session_id, seq)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_commands_status_id ON commands(status, id)"
            )
            conn.execute(
                "DELETE FROM gateway_credentials WHERE gateway_token NOT LIKE 'enc:v1:%'"
            )

    def set_gateway_credential(
        self,
        session_id: str,
        gateway_base_url: str,
        gateway_token: str,
        gateway_token_id: str,
        gateway_token_expire_at: int,
        scopes: list[str],
    ) -> None:
        now = int(time.time())
        encrypted_gateway_token = self._secret_cipher.encrypt(gateway_token)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO gateway_credentials(
                    session_id, gateway_base_url, gateway_token, gateway_token_id,
                    gateway_token_expire_at, scopes_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    gateway_base_url=excluded.gateway_base_url,
                    gateway_token=excluded.gateway_token,
                    gateway_token_id=excluded.gateway_token_id,
                    gateway_token_expire_at=excluded.gateway_token_expire_at,
                    scopes_json=excluded.scopes_json,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    gateway_base_url,
                    encrypted_gateway_token,
                    gateway_token_id,
                    gateway_token_expire_at,
                    json.dumps(scopes, ensure_ascii=False),
                    now,
                ),
            )

    def clear_gateway_credential(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM gateway_credentials WHERE session_id = ?", (session_id,))
            return cur.rowcount > 0

    def get_gateway_credential(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, gateway_base_url, gateway_token, gateway_token_id,
                       gateway_token_expire_at, scopes_json, updated_at
                FROM gateway_credentials
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        gateway_token_ciphertext = str(row["gateway_token"])
        gateway_token = self._secret_cipher.decrypt(gateway_token_ciphertext)
        return {
            "session_id": row["session_id"],
            "gateway_base_url": row["gateway_base_url"],
            "gateway_token": gateway_token,
            "gateway_token_id": row["gateway_token_id"],
            "gateway_token_expire_at": int(row["gateway_token_expire_at"]),
            "scopes": json.loads(row["scopes_json"] or "[]"),
            "updated_at": int(row["updated_at"]),
        }

    def has_gateway_credential(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM gateway_credentials WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    def upsert_run(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        status: str,
        message: str | None = None,
        error: str | None = None,
        reset_events: bool = False,
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT created_at FROM runs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            created_at = int(row["created_at"]) if row else now
            conn.execute(
                """
                INSERT INTO runs(
                    session_id, agent_id, user_id, status, message, error,
                    created_at, started_at, finished_at, last_heartbeat_at, next_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 1)
                ON CONFLICT(session_id) DO UPDATE SET
                    agent_id=excluded.agent_id,
                    user_id=excluded.user_id,
                    status=excluded.status,
                    message=excluded.message,
                    error=excluded.error,
                    last_heartbeat_at=excluded.last_heartbeat_at,
                    started_at=NULL,
                    finished_at=NULL,
                    next_seq=1
                """,
                (session_id, agent_id, user_id, status, message, error, created_at, now),
            )
            if reset_events:
                conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            conn.execute("COMMIT")
        return self.get_run(session_id) or {"session_id": session_id, "status": status}

    def update_run_status(
        self,
        session_id: str,
        status: str,
        *,
        error: str | None = None,
        set_started: bool = False,
        set_finished: bool = False,
    ) -> bool:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM runs WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return False
            updates = ["status = ?", "error = ?", "last_heartbeat_at = ?"]
            params: list[Any] = [status, error, now]
            if set_started:
                updates.append("started_at = ?")
                params.append(now)
            if set_finished:
                updates.append("finished_at = ?")
                params.append(now)
            params.append(session_id)
            conn.execute(
                f"UPDATE runs SET {', '.join(updates)} WHERE session_id = ?",
                tuple(params),
            )
            return True

    def touch_run_heartbeat(self, session_id: str) -> bool:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE runs SET last_heartbeat_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            return cur.rowcount > 0

    def get_run(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, agent_id, user_id, status, message, error,
                       created_at, started_at, finished_at, last_heartbeat_at, next_seq
                FROM runs
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "user_id": row["user_id"],
            "status": row["status"],
            "message": row["message"],
            "error": row["error"],
            "created_at": int(row["created_at"]),
            "started_at": int(row["started_at"]) if row["started_at"] is not None else None,
            "finished_at": int(row["finished_at"]) if row["finished_at"] is not None else None,
            "last_heartbeat_at": int(row["last_heartbeat_at"]),
            "next_seq": int(row["next_seq"]),
        }

    def delete_run(self, session_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            cur = conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
            return cur.rowcount > 0

    def append_event(self, session_id: str, event: str, data: dict[str, Any]) -> int:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT next_seq FROM runs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                raise ValueError(f"Run not found for session_id={session_id}")
            seq = int(row["next_seq"])
            conn.execute(
                """
                INSERT INTO events(session_id, seq, event, data_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, seq, event, json.dumps(data, ensure_ascii=False), now),
            )
            conn.execute(
                """
                UPDATE runs
                SET next_seq = ?, last_heartbeat_at = ?
                WHERE session_id = ?
                """,
                (seq + 1, now, session_id),
            )
            conn.execute("COMMIT")
        return seq

    def get_events(self, session_id: str, from_seq: int = 1, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, event, data_json, timestamp
                FROM events
                WHERE session_id = ? AND seq >= ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (session_id, from_seq, limit),
            ).fetchall()
        return [
            {
                "seq": int(row["seq"]),
                "event": row["event"],
                "data": json.loads(row["data_json"] or "{}"),
                "timestamp": int(row["timestamp"]),
            }
            for row in rows
        ]

    def enqueue_command(self, session_id: str, command_type: str, payload: dict[str, Any]) -> int:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO commands(session_id, command_type, payload_json, status, error, created_at, processed_at)
                VALUES (?, ?, ?, 'pending', NULL, ?, NULL)
                """,
                (session_id, command_type, json.dumps(payload, ensure_ascii=False), now),
            )
            return int(cur.lastrowid)

    def get_pending_commands(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, command_type, payload_json, status, created_at
                FROM commands
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "session_id": row["session_id"],
                "command_type": row["command_type"],
                "payload": json.loads(row["payload_json"] or "{}"),
                "status": row["status"],
                "created_at": int(row["created_at"]),
            }
            for row in rows
        ]

    def mark_command_done(self, command_id: int) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE commands
                SET status = 'done', processed_at = ?, error = NULL
                WHERE id = ?
                """,
                (now, command_id),
            )

    def mark_command_failed(self, command_id: int, error: str) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE commands
                SET status = 'failed', processed_at = ?, error = ?
                WHERE id = ?
                """,
                (now, error, command_id),
            )


runtime_store = RuntimeStore()
