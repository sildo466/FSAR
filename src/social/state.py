"""SQLite persistence for social sessions, bindings, and adapter cursors."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from src.memory.db import db_path


_DEFAULT_USER_CARD_ID = 1


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(str(db_path()))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_or_create_session(platform: str, peer_id: str) -> str:
    with _conn() as connection:
        row = connection.execute(
            "SELECT id FROM sessions WHERE source_platform=? AND source_peer_id=?",
            (platform, peer_id),
        ).fetchone()
        if row:
            return str(row["id"])

        session_id = uuid.uuid4().hex
        now = _now_iso()
        connection.execute(
            "INSERT INTO sessions "
            "(id, title, pinned, created_at, updated_at, message_count, "
            "source_platform, source_peer_id) "
            "VALUES (?, ?, 0, ?, ?, 0, ?, ?)",
            (session_id, f"{platform}:{peer_id}", now, now, platform, peer_id),
        )
        return session_id


def load_session_messages(session_id: str, limit: int = 20) -> list[dict[str, str]]:
    with _conn() as connection:
        rows = connection.execute(
            "SELECT role, content FROM conversations "
            "WHERE session_fk=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    messages = [
        {"role": str(row["role"]), "content": str(row["content"])}
        for row in reversed(rows)
    ]
    # Legacy sessions may contain consecutive duplicate rows written by the
    # old double-persistence bridge; collapse them so the model never imitates
    # the duplication pattern.
    collapsed: list[dict[str, str]] = []
    for message in messages:
        if collapsed and collapsed[-1] == message:
            continue
        collapsed.append(message)
    return collapsed


def append_session_message(session_id: str, role: str, content: str) -> None:
    now = _now_iso()
    with _conn() as connection:
        connection.execute(
            "INSERT INTO conversations "
            "(session_id, session_fk, role, content, summary, tags, timestamp) "
            "VALUES (?, ?, ?, ?, '', '', ?)",
            (session_id, session_id, role, content, now),
        )
        connection.execute(
            "UPDATE sessions SET updated_at=?, message_count=message_count + 1 "
            "WHERE id=?",
            (now, session_id),
        )


def upsert_binding(
    platform: str,
    peer_id: str,
    *,
    display_name: str | None = None,
    fsar_user_card_id: int = _DEFAULT_USER_CARD_ID,
) -> None:
    now = _now_iso()
    with _conn() as connection:
        connection.execute(
            """
            INSERT INTO social_bindings(
                platform, peer_id, fsar_user_card_id, display_name,
                bound_at, last_seen_at, muted
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(platform, peer_id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                display_name=COALESCE(
                    excluded.display_name,
                    social_bindings.display_name
                )
            """,
            (platform, peer_id, fsar_user_card_id, display_name, now, now),
        )


def touch_binding(platform: str, peer_id: str) -> None:
    with _conn() as connection:
        connection.execute(
            "UPDATE social_bindings SET last_seen_at=? "
            "WHERE platform=? AND peer_id=?",
            (_now_iso(), platform, peer_id),
        )


def is_muted(platform: str, peer_id: str) -> bool:
    with _conn() as connection:
        row = connection.execute(
            "SELECT muted FROM social_bindings WHERE platform=? AND peer_id=?",
            (platform, peer_id),
        ).fetchone()
        return bool(row and row["muted"])


def load_cursor(platform: str) -> dict:
    with _conn() as connection:
        row = connection.execute(
            "SELECT state_json FROM social_state WHERE platform=?",
            (platform,),
        ).fetchone()
        if not row:
            return {}
        try:
            cursor = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            return {}
        return cursor if isinstance(cursor, dict) else {}


def save_cursor(platform: str, cursor: dict) -> None:
    with _conn() as connection:
        connection.execute(
            """
            INSERT INTO social_state(platform, state_json) VALUES (?, ?)
            ON CONFLICT(platform) DO UPDATE SET state_json=excluded.state_json
            """,
            (platform, json.dumps(cursor)),
        )
