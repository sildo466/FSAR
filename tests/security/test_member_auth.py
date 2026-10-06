# SPDX-License-Identifier: MIT
"""The single decision about whether a room credential may be used."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.memory.member_tokens import MemberTokenStore
from src.security.member_auth import REASONS, authorize_member

ANCHOR = "192.168.1.20"
ELSEWHERE = "10.0.0.9"


@pytest.fixture()
def store() -> MemberTokenStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return MemberTokenStore(Path(tmp.name) / "tokens.db")


def _issue(store: MemberTokenStore, **kwargs):
    return store.issue(1, "claude-laptop", **kwargs)


def test_a_fresh_token_authorizes_and_anchors_its_address(store) -> None:
    issued = _issue(store)
    outcome = authorize_member(store, issued.token, source_ip=ANCHOR)
    assert outcome.ok is True
    assert outcome.reason == "ok"
    assert outcome.room_id == 1
    assert outcome.member_ref == "claude-laptop"
    assert outcome.token_id == issued.token_id
    assert outcome.first_bind is True
    assert outcome.bound_ip == ANCHOR
    assert store.resolve_record(issued.token).bound_ip == ANCHOR


def test_the_same_address_keeps_working(store) -> None:
    issued = _issue(store)
    authorize_member(store, issued.token, source_ip=ANCHOR)
    second = authorize_member(store, issued.token, source_ip=ANCHOR)
    assert second.ok is True
    assert second.first_bind is False


def test_another_address_is_refused(store) -> None:
    issued = _issue(store)
    authorize_member(store, issued.token, source_ip=ANCHOR)
    outcome = authorize_member(store, issued.token, source_ip=ELSEWHERE)
    assert outcome.ok is False
    assert outcome.reason == "ip_mismatch"
    assert outcome.bound_ip == ANCHOR
    # The refusal must not move the anchor.
    assert store.resolve_record(issued.token).bound_ip == ANCHOR


def test_a_rebound_token_accepts_the_new_address(store) -> None:
    issued = _issue(store)
    authorize_member(store, issued.token, source_ip=ANCHOR)
    assert store.rebind_ip(issued.token_id, ELSEWHERE) is True
    assert authorize_member(store, issued.token, source_ip=ELSEWHERE).ok is True


def test_an_empty_token_is_not_a_token(store) -> None:
    outcome = authorize_member(store, "", source_ip=ANCHOR)
    assert outcome.ok is False
    assert outcome.reason == "no_token"


def test_an_unknown_token(store) -> None:
    outcome = authorize_member(store, "not-a-token", source_ip=ANCHOR)
    assert outcome.reason == "token_unknown"
    assert outcome.room_id is None


def test_a_revoked_token(store) -> None:
    issued = _issue(store)
    store.revoke(issued.token_id)
    outcome = authorize_member(store, issued.token, source_ip=ANCHOR)
    assert outcome.reason == "token_revoked"
    # The audit still learns whose credential it was.
    assert outcome.member_ref == "claude-laptop"


def test_a_revoked_and_expired_token_reports_revoked(store) -> None:
    """Revocation wins: it is the action somebody took on purpose."""
    issued = _issue(store, ttl_seconds=-1)
    store.revoke(issued.token_id)
    assert authorize_member(
        store, issued.token, source_ip=ANCHOR
    ).reason == "token_revoked"


def test_an_expired_token(store) -> None:
    issued = _issue(store, ttl_seconds=60)
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    outcome = authorize_member(store, issued.token, source_ip=ANCHOR, now=later)
    assert outcome.ok is False
    assert outcome.reason == "token_expired"


def test_expiry_includes_the_boundary(store) -> None:
    issued = _issue(store, ttl_seconds=60)
    exactly = datetime.fromisoformat(store.resolve_record(issued.token).expires_at)
    assert authorize_member(
        store, issued.token, source_ip=ANCHOR, now=exactly
    ).reason == "token_expired"


def test_a_token_without_expiry_works_far_in_the_future(store) -> None:
    issued = _issue(store, ttl_seconds=None)
    later = datetime.now(timezone.utc) + timedelta(days=3650)
    assert authorize_member(
        store, issued.token, source_ip=ANCHOR, now=later
    ).ok is True


def test_a_successful_call_marks_the_use(store) -> None:
    issued = _issue(store)
    authorize_member(store, issued.token, source_ip=ANCHOR)
    record = store.resolve_record(issued.token)
    assert record.last_used_at is not None
    assert record.last_used_ip == ANCHOR


def test_a_refused_call_does_not_mark_the_use(store) -> None:
    issued = _issue(store)
    authorize_member(store, issued.token, source_ip=ANCHOR)
    authorize_member(store, issued.token, source_ip=ELSEWHERE)
    assert store.resolve_record(issued.token).last_used_ip == ANCHOR


def test_a_lost_first_bind_race_is_not_a_failure(store) -> None:
    """Two simultaneous first connections: the loser still gets in, and the
    anchor belongs to the winner."""
    issued = _issue(store)
    assert store.bind_ip(issued.token_id, ANCHOR) is True
    assert store.bind_ip(issued.token_id, ELSEWHERE) is False
    assert store.resolve_record(issued.token).bound_ip == ANCHOR
    assert authorize_member(store, issued.token, source_ip=ANCHOR).ok is True


def test_a_banned_token(store) -> None:
    issued = _issue(store)
    assert store.ban(issued.token_id, "abuse") is True
    outcome = authorize_member(store, issued.token, source_ip=ANCHOR)
    assert outcome.ok is False
    assert outcome.reason == "token_banned"
    # The audit still learns whose credential it was.
    assert outcome.member_ref == "claude-laptop"


def test_a_ban_is_not_a_revoke(store) -> None:
    """Two different things: one the owner did, one this side did for them.
    The owner has to be able to tell them apart to lift only the second."""
    issued = _issue(store)
    store.ban(issued.token_id, "abuse")
    record = store.resolve_record(issued.token)
    assert record.revoked_at is None
    assert record.banned_at is not None
    assert record.banned_reason == "abuse"


def test_a_revoked_and_banned_token_reports_revoked(store) -> None:
    issued = _issue(store)
    store.revoke(issued.token_id)
    store.ban(issued.token_id, "abuse")
    assert authorize_member(
        store, issued.token, source_ip=ANCHOR
    ).reason == "token_revoked"


def test_a_banned_token_neither_anchors_nor_marks_a_use(store) -> None:
    """A refusal changes nothing — including this one."""
    issued = _issue(store)
    store.ban(issued.token_id, "injection")
    authorize_member(store, issued.token, source_ip=ANCHOR)
    record = store.resolve_record(issued.token)
    assert record.bound_ip is None
    assert record.last_used_at is None


def test_lifting_a_ban_restores_the_credential(store) -> None:
    issued = _issue(store)
    store.ban(issued.token_id, "abuse")
    assert store.unban(issued.token_id) is True
    assert authorize_member(store, issued.token, source_ip=ANCHOR).ok is True
    assert store.resolve_record(issued.token).banned_reason is None


def test_the_reason_enum_is_exactly_these(store) -> None:
    assert set(REASONS) == {
        "ok", "no_token", "token_unknown", "token_revoked", "token_banned",
        "token_expired", "ip_mismatch",
    }


def test_reasons_stay_distinguishable_for_the_audit(store) -> None:
    """Precise reasons exist so an incident is diagnosable; collapsing them
    into one response is the HTTP layer's job, not this function's."""
    issued = _issue(store)
    store.revoke(issued.token_id)
    reasons = {
        authorize_member(store, issued.token, source_ip=ANCHOR).reason,
        authorize_member(store, "nope", source_ip=ANCHOR).reason,
    }
    assert reasons == {"token_revoked", "token_unknown"}
