# SPDX-License-Identifier: MIT
"""Token expiry, the TOFU source anchor, and full record lookup."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.memory.member_tokens import DEFAULT_TTL_SECONDS, MemberTokenStore


def _store() -> MemberTokenStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return MemberTokenStore(Path(tmp.name) / "tokens.db")


def test_issue_sets_a_seven_day_expiry_by_default() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    record = store.resolve_record(issued.token)
    assert record is not None
    assert record.expires_at is not None
    delta = datetime.fromisoformat(record.expires_at) - datetime.now(timezone.utc)
    assert timedelta(days=6) < delta < timedelta(days=8)
    assert DEFAULT_TTL_SECONDS == 7 * 24 * 3600


def test_issue_reports_the_expiry_it_wrote() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    assert issued.expires_at == store.resolve_record(issued.token).expires_at


def test_a_token_can_be_made_that_never_expires() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop", ttl_seconds=None)
    assert store.resolve_record(issued.token).expires_at is None
    assert issued.expires_at is None


def test_a_custom_ttl_is_honoured() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop", ttl_seconds=60)
    expires = datetime.fromisoformat(store.resolve_record(issued.token).expires_at)
    assert expires - datetime.now(timezone.utc) < timedelta(minutes=5)


def test_a_revoked_token_still_resolves_as_a_record() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    store.revoke(issued.token_id)
    record = store.resolve_record(issued.token)
    assert record is not None
    assert record.revoked_at is not None
    # The tuple-shaped P1 accessor still hides it.
    assert store.resolve(issued.token) is None


def test_an_expired_token_is_hidden_from_the_tuple_accessor() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop", ttl_seconds=-1)
    assert store.resolve(issued.token) is None
    assert store.resolve_record(issued.token) is not None


def test_an_unknown_token_has_no_record() -> None:
    assert _store().resolve_record("nope") is None
    assert _store().resolve_record("") is None


def test_bind_ip_is_a_one_way_anchor() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    assert store.bind_ip(issued.token_id, "192.168.1.20") is True
    assert store.bind_ip(issued.token_id, "10.0.0.9") is False
    assert store.resolve_record(issued.token).bound_ip == "192.168.1.20"


def test_rebind_overrides_the_anchor() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    store.bind_ip(issued.token_id, "192.168.1.20")
    assert store.rebind_ip(issued.token_id, "192.168.1.77") is True
    assert store.resolve_record(issued.token).bound_ip == "192.168.1.77"


def test_rebind_on_an_unknown_token_is_false() -> None:
    assert _store().rebind_ip(999, "192.168.1.20") is False


def test_note_use_records_the_source_address() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    store.note_use(issued.token_id, "192.168.1.20")
    record = store.resolve_record(issued.token)
    assert record.last_used_ip == "192.168.1.20"
    assert record.last_used_at is not None


def test_list_for_reports_expiry_and_binding() -> None:
    store = _store()
    issued = store.issue(1, "claude-laptop")
    store.bind_ip(issued.token_id, "192.168.1.20")
    row = store.list_for(1, "claude-laptop")[0]
    assert row["bound_ip"] == "192.168.1.20"
    assert row["expires_at"] is not None


def test_a_p1_row_migrates_and_reads_back(tmp_path: Path) -> None:
    """The real migration risk: a row written before these columns existed."""
    db = tmp_path / "old.db"
    token = "plaintext-token-from-p1"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE room_member_tokens (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash   TEXT NOT NULL UNIQUE,
                room_id      INTEGER NOT NULL,
                member_ref   TEXT NOT NULL,
                label        TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at   TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO room_member_tokens "
            "(token_hash, room_id, member_ref, label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), 4, "old-member",
             "from p1", "2026-09-01T00:00:00+00:00"),
        )
        conn.commit()

    store = MemberTokenStore(db)  # runs the ALTERs
    record = store.resolve_record(token)
    assert record is not None
    assert record.member_ref == "old-member"
    assert record.room_id == 4
    assert record.expires_at is None
    assert record.bound_ip is None
    assert record.last_used_ip is None
    # A pre-P2 token has no expiry, so the P1 accessor keeps accepting it.
    assert store.resolve(token) == (4, "old-member")


def test_reopening_does_not_lose_the_anchor(tmp_path: Path) -> None:
    db = tmp_path / "tokens.db"
    issued = MemberTokenStore(db).issue(1, "claude-laptop")
    MemberTokenStore(db).bind_ip(issued.token_id, "192.168.1.20")
    again = MemberTokenStore(db)
    assert again.resolve_record(issued.token).bound_ip == "192.168.1.20"
