# SPDX-License-Identifier: MIT
"""Append-only identity audit for the LAN surface."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.memory.auth_audit import ACTIONS, RESULTS, AuthAuditStore


def _store() -> AuthAuditStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return AuthAuditStore(Path(tmp.name) / "audit.db")


def test_append_then_list_newest_first() -> None:
    store = _store()
    store.append(action="lan_message", result="allow", reason="ok",
                 room_id=1, member_ref="claude-laptop")
    store.append(action="lan_message", result="deny", reason="token_expired",
                 room_id=1, member_ref="claude-laptop")
    rows = store.list()
    assert [r["result"] for r in rows] == ["deny", "allow"]


def test_sequence_is_monotonic() -> None:
    store = _store()
    first = store.append(action="token_issued", result="allow", reason="ok")
    second = store.append(action="token_revoked", result="allow", reason="ok")
    assert second == first + 1


def test_list_can_be_scoped_to_a_room() -> None:
    store = _store()
    store.append(action="lan_message", result="allow", reason="ok", room_id=1)
    store.append(action="lan_message", result="allow", reason="ok", room_id=2)
    assert len(store.list(room_id=1)) == 1


def test_list_limits() -> None:
    store = _store()
    for _ in range(5):
        store.append(action="lan_read", result="allow", reason="ok")
    assert len(store.list(limit=2)) == 2


def test_every_field_survives_the_round_trip() -> None:
    store = _store()
    store.append(
        action="lan_auth", result="deny", reason="ip_mismatch", room_id=3,
        member_ref="claude-laptop", token_id=12, source_ip="10.0.0.9",
        request_id="req-1", detail="since=0",
    )
    row = store.list()[0]
    assert row["action"] == "lan_auth"
    assert row["reason"] == "ip_mismatch"
    assert row["room_id"] == 3
    assert row["member_ref"] == "claude-laptop"
    assert row["token_id"] == 12
    assert row["source_ip"] == "10.0.0.9"
    assert row["request_id"] == "req-1"
    assert row["detail"] == "since=0"


def test_no_secret_ever_lands_in_the_table() -> None:
    store = _store()
    store.append(action="lan_auth", result="deny", reason="token_unknown",
                 source_ip="192.168.1.20", request_id="req-1")
    with sqlite3.connect(store.db_path) as conn:
        blob = " ".join(
            str(value)
            for row in conn.execute("SELECT * FROM auth_audit")
            for value in row
        )
    assert "Bearer" not in blob
    assert "token_hash" not in blob


def test_action_must_be_known() -> None:
    store = _store()
    with pytest.raises(ValueError):
        store.append(action="not_a_real_action", result="allow", reason="ok")


def test_result_must_be_known() -> None:
    store = _store()
    with pytest.raises(ValueError):
        store.append(action="lan_auth", result="maybe", reason="ok")


def test_the_enums_are_not_empty() -> None:
    assert "lan_auth" in ACTIONS
    assert "ip_blocked" in ACTIONS
    assert set(RESULTS) == {"allow", "deny"}


def test_timestamps_are_iso() -> None:
    store = _store()
    store.append(action="lan_auth", result="allow", reason="ok")
    assert "T" in store.list()[0]["created_at"]


def test_optional_fields_default_to_null() -> None:
    store = _store()
    store.append(action="lan_auth", result="allow", reason="ok")
    row = store.list()[0]
    assert row["room_id"] is None
    assert row["source_ip"] is None
    assert row["detail"] == ""


def test_survives_a_reopen() -> None:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = Path(tmp.name) / "audit.db"
    AuthAuditStore(db).append(action="token_issued", result="allow", reason="ok")
    assert len(AuthAuditStore(db).list()) == 1
