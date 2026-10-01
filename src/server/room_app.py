# SPDX-License-Identifier: MIT
"""The LAN-facing room API.

A separate app from the GUI server on purpose: containment by construction.
Tool execution, file access, member management, room settings and promotion
have no routes here at all, so there is nothing to authorize — as opposed to
being authorized and then refused.

Identity always comes from the credential. No request body may name a room or
a member, and no handler reads either from anything but the token.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.security.member_auth import AuthOutcome, authorize_member
from src.security.rate_budget import RateBudget
from src.security.visitor_screen import VisitorVerdict
from src.security.ws_auth import bearer_token

# Budgets, as (limit, window_seconds, burst).
READ_BUDGET = (120, 60.0, 10)
SPEAK_BUDGET = (20, 60.0, 5)
ROOM_SPEAK_BUDGET = (60, 60.0, 10)
UNAUTH_BUDGET = (30, 60.0, 10)
# A patch is an hour's work, not a remark, so the allowance is far smaller.
PATCH_BUDGET = (10, 60.0, 3)

MAX_CONTENT_BYTES = 16 * 1024
MAX_BODY_BYTES = 64 * 1024
MAX_PATCH_BYTES = 512 * 1024
IDEMPOTENCY_TTL_SECONDS = 24 * 3600
STATE_PAGE_LIMIT = 100
# One alert per credential+address per minute. A rejected request is something
# an attacker can repeat, and an alert per attempt would fill the owner's
# notifications instead of informing them.
ALERT_BUDGET = (1, 60.0, 1)


@dataclass
class RoomDeps:
    tokens: Any
    blocklist: Any
    audit: Any
    rooms: Any
    members: Any
    budget: RateBudget
    idempotency: Any = None
    cards: Any = None
    notify: Callable[[str, str, str], None] | None = None
    visitor_screen: Any = None
    plans: Any = None
    publishes: Any = None
    patches: Any = None
    history_limit: int = STATE_PAGE_LIMIT


def client_ip(request: Request) -> str:
    """The peer address, never a forwarded header: nothing upstream is trusted
    to speak for anyone, and a spoofable header would forge the TOFU anchor."""
    return request.client.host if request.client else ""


def uniform_error(code: str, request_id: str) -> dict[str, str]:
    return {"code": code, "request_id": request_id}


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def audit(deps: RoomDeps, request: Request, **fields: Any) -> None:
    """Best effort: a failed audit write must not turn a refusal into a 500
    that reads like an outage."""
    try:
        deps.audit.append(
            source_ip=client_ip(request),
            request_id=request_id_of(request),
            **fields,
        )
    except Exception:
        pass


def ip_mismatch_alert(deps: RoomDeps, outcome: AuthOutcome, ip: str) -> None:
    """Tell the owner that a credential arrived from a new address.

    This is the compensation for choosing TOFU: its refusal is otherwise
    silent, and a silent refusal reads like a network problem. The body
    carries no credential — notifications get screenshotted and forwarded.
    """
    if deps.notify is None:
        return
    limit, per_seconds, burst = ALERT_BUDGET
    if not deps.budget.allow(
        f"alert:{outcome.token_id}:{ip}", limit=limit,
        per_seconds=per_seconds, burst=burst,
    ):
        return
    bound = outcome.bound_ip or "an unknown address"
    member = None
    if deps.members is not None and outcome.room_id is not None:
        member = deps.members.get(outcome.room_id, outcome.member_ref)
    display = getattr(member, "display_name", "") or outcome.member_ref
    try:
        deps.notify(
            f"Room credential used from a new address ({display})",
            f"Member {outcome.member_ref}: bound to {bound}; this request came "
            f"from {ip}. Rebind it if the machine moved, or revoke it if it "
            f"did not.",
            f"lan-ip-mismatch:{outcome.token_id}:{ip}",
        )
    except Exception:
        # Best effort: an alert must never turn a refusal into a 500.
        pass


def ban_visitor(
    deps: RoomDeps, request: Request, outcome: AuthOutcome,
    verdict: VisitorVerdict, content: str,
) -> None:
    """Take the credential away, then tell the owner.

    The ban is the control, so it is not made best effort: letting a failed
    write out as a 500 keeps the line out of the room, where swallowing it
    would post the very line the screen just refused. The notification is best
    effort — a notification failure must not turn a refusal into an outage.

    The body carries the line. Every other alert here avoids content, but
    deciding whether to lift a ban means reading what was said.
    """
    deps.tokens.ban(outcome.token_id, verdict.category)
    audit(
        deps, request, action="lan_message", result="deny",
        reason=f"visitor_{verdict.category}", room_id=outcome.room_id,
        member_ref=outcome.member_ref, token_id=outcome.token_id,
        detail=f"route={verdict.route} confidence={verdict.confidence:.2f}",
    )
    if deps.notify is None:
        return
    member = None
    if deps.members is not None and outcome.room_id is not None:
        member = deps.members.get(outcome.room_id, outcome.member_ref)
    display = getattr(member, "display_name", "") or outcome.member_ref
    # Keyed by the line, so a repeat of the same abuse does not stack
    # notifications while a different one still raises its own.
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    try:
        deps.notify(
            f"Banned a room member ({display})",
            f"Member {outcome.member_ref} sent a line read as "
            f"{verdict.category} ({verdict.reason or verdict.route}). Their "
            f"credential is banned and stops working immediately; restore it "
            f"from the room's member panel if this was wrong.\n\n{content[:300]}",
            f"lan-ban:{outcome.token_id}:{digest}",
        )
    except Exception:
        pass


def auth_guard(deps: RoomDeps, request: Request) -> AuthOutcome:
    """Blocklist -> credential -> expiry -> address anchor, in that order.

    Every refusal is the same 401, so neither the blocklist nor the reason can
    be observed from outside; the precise reason goes to the audit instead.
    """
    ip = client_ip(request)

    if deps.blocklist.is_blocked(ip):
        audit(deps, request, action="ip_blocked", result="deny", reason="ip_blocked")
        raise HTTPException(status_code=401, detail="unauthorized")

    token = bearer_token(request.headers.get("authorization"))
    outcome = authorize_member(deps.tokens, token, source_ip=ip)

    if not outcome.ok:
        limit, per_seconds, burst = UNAUTH_BUDGET
        if not deps.budget.allow(
            f"unauth:{ip}", limit=limit, per_seconds=per_seconds, burst=burst,
        ):
            audit(deps, request, action="lan_auth", result="deny",
                  reason="rate_limited")
            raise HTTPException(status_code=429, detail="rate_limited")
        audit(deps, request, action="lan_auth", result="deny",
              reason=outcome.reason, room_id=outcome.room_id,
              member_ref=outcome.member_ref, token_id=outcome.token_id)
        if outcome.reason == "ip_mismatch":
            ip_mismatch_alert(deps, outcome, ip)
        raise HTTPException(status_code=401, detail="unauthorized")

    return outcome


def require_room(
    deps: RoomDeps, request: Request, room_id: int, outcome: AuthOutcome,
) -> Any:
    """The room must exist, be the token's own room, have LAN on, and the
    membership must still be there. All four failures are one 404: a room the
    caller may not use must be indistinguishable from one that is absent."""
    def _refuse(reason: str) -> None:
        audit(deps, request, action="lan_read", result="deny", reason=reason,
              room_id=room_id, member_ref=outcome.member_ref,
              token_id=outcome.token_id)
        raise HTTPException(status_code=404, detail="not_found")

    if outcome.room_id != room_id:
        _refuse("room_not_authorized")
    room = deps.rooms.get(room_id) if deps.rooms is not None else None
    if room is None or not getattr(room, "lan_enabled", False):
        _refuse("room_lan_off")
    if deps.members is None or deps.members.get(room_id, outcome.member_ref) is None:
        _refuse("membership_gone")
    return room


async def read_body(request: Request, limit: int | None = None) -> bytes:
    """Read the body with the size cap enforced as it arrives.

    `await request.body()` buffers whatever the caller sent before any check
    can run, so the limit would only ever describe a body already in memory.
    Read in chunks and stop at the cap instead. The cap is read at call time
    so a patched value applies."""
    cap = MAX_BODY_BYTES if limit is None else limit
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            raise HTTPException(status_code=413, detail="too_long")
        chunks.append(chunk)
    return b"".join(chunks)


def read_json_object(
    request: Request, raw: bytes, limit: int | None = None,
) -> dict[str, Any]:
    """Strict body parsing: unknown fields, duplicate keys and non-objects are
    refused, because an extra field is how a caller tries to name a room."""
    cap = MAX_BODY_BYTES if limit is None else limit
    if not raw:
        raise HTTPException(status_code=400, detail="bad_json")
    if len(raw) > cap:
        # "Too large" is its own answer: a caller sending an oversized body has
        # not written malformed JSON, and 400 would send it looking for a bug.
        raise HTTPException(status_code=413, detail="too_long")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="bad_json")
    seen: list[str] = []

    def _hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen.extend(key for key, _ in pairs)
        return dict(pairs)

    try:
        parsed = json.loads(text, object_pairs_hook=_hook)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="bad_json")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="bad_json")
    if len(seen) != len(set(seen)):
        raise HTTPException(status_code=400, detail="duplicate_key")
    return parsed


def create_room_app(deps: RoomDeps) -> FastAPI:
    app = FastAPI(
        title="FSAR room API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def _harden(request: Request, call_next):
        request.state.request_id = secrets.token_hex(8)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "error"
        code = detail
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 405:
            code = "method_not_allowed"
        return JSONResponse(
            status_code=exc.status_code,
            content=uniform_error(code, request_id_of(request)),
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(Exception)
    async def _crash(request: Request, exc: Exception):
        # Never let a stack trace or a SQL string reach the network.
        return JSONResponse(
            status_code=500,
            content=uniform_error("internal_error", request_id_of(request)),
            headers={"Cache-Control": "no-store"},
        )

    from src.server.room_routes import register_routes

    register_routes(app, deps)
    return app
