# SPDX-License-Identifier: MIT
"""Per-member room credentials are stored as a hash, never in the clear."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.memory.member_tokens import MemberTokenStore


@pytest.fixture()
def store() -> MemberTokenStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return MemberTokenStore(Path(tmp.name) / "tokens.db")


def test_issue_then_resolve(store: MemberTokenStore) -> None:
    issued = store.issue(1, "claude-laptop")
    assert store.resolve(issued.token) == (1, "claude-laptop")


def test_plaintext_is_never_stored(store: MemberTokenStore) -> None:
    issued = store.issue(1, "claude-laptop")
    with sqlite3.connect(store.db_path) as conn:
        blob = " ".join(
            str(v) for row in conn.execute("SELECT * FROM room_member_tokens")
            for v in row
        )
    assert issued.token not in blob
    assert hashlib.sha256(issued.token.encode()).hexdigest() in blob


def test_unknown_token_resolves_to_none(store: MemberTokenStore) -> None:
    assert store.resolve("not-a-token") is None
    assert store.resolve("") is None


def test_revoked_token_stops_resolving(store: MemberTokenStore) -> None:
    issued = store.issue(1, "claude-laptop")
    assert store.revoke(issued.token_id) is True
    assert store.resolve(issued.token) is None


def test_revoke_is_idempotent_and_reports(store: MemberTokenStore) -> None:
    issued = store.issue(1, "claude-laptop")
    assert store.revoke(issued.token_id) is True
    assert store.revoke(issued.token_id) is False


def test_resolve_records_last_used(store: MemberTokenStore) -> None:
    issued = store.issue(1, "claude-laptop")
    before = store.list_for(1, "claude-laptop")[0]
    assert before["last_used_at"] is None
    store.resolve(issued.token)
    after = store.list_for(1, "claude-laptop")[0]
    assert after["last_used_at"] is not None


def test_two_tokens_for_the_same_member_are_independent(
    store: MemberTokenStore,
) -> None:
    first = store.issue(1, "claude-laptop", label="old laptop")
    second = store.issue(1, "claude-laptop", label="new laptop")
    assert store.resolve(first.token) == (1, "claude-laptop")
    assert store.resolve(second.token) == (1, "claude-laptop")
    store.revoke(first.token_id)
    assert store.resolve(first.token) is None
    assert store.resolve(second.token) == (1, "claude-laptop")


def test_list_for_omits_the_secret(store: MemberTokenStore) -> None:
    store.issue(1, "claude-laptop", label="laptop")
    rows = store.list_for(1, "claude-laptop")
    assert len(rows) == 1
    assert rows[0]["label"] == "laptop"
    assert "token" not in rows[0]
    assert "token_hash" not in rows[0]


def test_tokens_are_unique_across_issues(store: MemberTokenStore) -> None:
    tokens = {store.issue(1, f"m{i}").token for i in range(5)}
    assert len(tokens) == 5
