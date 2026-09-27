# SPDX-License-Identifier: MIT
"""The single place that decides whether a room credential may be used.

It returns a precise reason so the audit can say what actually happened, and
collapses nothing: the HTTP layer is what turns every refusal into one
`401 unauthorized`, which is the anti-enumeration requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

REASONS = (
    "ok",
    "no_token",
    "token_unknown",
    "token_revoked",
    "token_banned",
    "token_expired",
    "ip_mismatch",
)


@dataclass
class AuthOutcome:
    ok: bool
    reason: str
    room_id: int | None = None
    member_ref: str | None = None
    token_id: int | None = None
    bound_ip: str | None = None
    first_bind: bool = False


def authorize_member(
    store,
    token: str,
    *,
    source_ip: str,
    now: datetime | None = None,
) -> AuthOutcome:
    """Validate one credential for one request.

    Two side effects, both narrow: the first successful use anchors the source
    address, and a successful use stamps last_used_at / last_used_ip. Refusals
    change nothing — a rejected request must not move the anchor, nor make a
    stolen credential look freshly used.
    """
    if not token:
        return AuthOutcome(ok=False, reason="no_token")

    record = store.resolve_record(token)
    if record is None:
        return AuthOutcome(ok=False, reason="token_unknown")
    if record.revoked_at is not None:
        return AuthOutcome(
            ok=False, reason="token_revoked", room_id=record.room_id,
            member_ref=record.member_ref, token_id=record.token_id,
        )
    if record.banned_at is not None:
        # Checked here rather than in the route so that a ban closes every
        # route at once, and so the audit says "banned" and not "revoked".
        return AuthOutcome(
            ok=False, reason="token_banned", room_id=record.room_id,
            member_ref=record.member_ref, token_id=record.token_id,
        )

    current = now or datetime.now(timezone.utc)
    if record.expires_at is not None:
        if datetime.fromisoformat(record.expires_at) <= current:
            return AuthOutcome(
                ok=False, reason="token_expired", room_id=record.room_id,
                member_ref=record.member_ref, token_id=record.token_id,
            )

    first_bind = False
    if record.bound_ip is None:
        # Losing this race means somebody else's first connection just won the
        # anchor; that is a shared credential, which the caller surfaces, not
        # a reason to refuse this request.
        first_bind = store.bind_ip(record.token_id, source_ip)
    elif record.bound_ip != source_ip:
        return AuthOutcome(
            ok=False, reason="ip_mismatch", room_id=record.room_id,
            member_ref=record.member_ref, token_id=record.token_id,
            bound_ip=record.bound_ip,
        )

    store.note_use(record.token_id, source_ip)
    return AuthOutcome(
        ok=True, reason="ok", room_id=record.room_id,
        member_ref=record.member_ref, token_id=record.token_id,
        bound_ip=record.bound_ip or source_ip, first_bind=first_bind,
    )
