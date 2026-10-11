# SPDX-License-Identifier: MIT
"""The dashboard's own credentials: one session, handed out once per launch.

This is not an account system. It exists so that "whoever can reach the port"
becomes "the browser the launcher opened" — the ticket a WebSocket handshake
carries is single-use and short-lived, and the cookie never travels there.
Everything lives in memory, so a restart is a logout, which is the point.
"""
from __future__ import annotations

import ipaddress
import secrets
import threading
import time

ADMIN_COOKIE = "fsar_admin"
TICKET_TTL_SECONDS = 60.0


def is_loopback(host: str) -> bool:
    """Address, not name: a caller picks its own Host header, but not its
    socket peer."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


class AdminSessions:
    def __init__(self, ticket_ttl: float = TICKET_TTL_SECONDS) -> None:
        self._ticket_ttl = ticket_ttl
        self._lock = threading.RLock()
        self._sessions: set[str] = set()
        self._tickets: dict[str, tuple[str, float]] = {}
        self._bootstrap = ""

    def rotate_bootstrap(self) -> str:
        with self._lock:
            self._bootstrap = secrets.token_urlsafe(32)
            return self._bootstrap

    def consume_bootstrap(self, value: str) -> str | None:
        with self._lock:
            if not value or not self._bootstrap:
                return None
            if not secrets.compare_digest(self._bootstrap, value):
                return None
            self._bootstrap = ""
            return self.create_session()

    def create_session(self) -> str:
        session = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions.add(session)
        return session

    def session_valid(self, session: str) -> bool:
        with self._lock:
            return bool(session) and session in self._sessions

    def issue_ticket(self, session: str, *, now: float | None = None) -> str | None:
        if not self.session_valid(session):
            return None
        current = time.monotonic() if now is None else now
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._prune(current)
            self._tickets[ticket] = (session, current + self._ticket_ttl)
        return ticket

    def consume_ticket(self, ticket: str, *, now: float | None = None) -> bool:
        if not ticket:
            return False
        current = time.monotonic() if now is None else now
        with self._lock:
            self._prune(current)
            entry = self._tickets.pop(ticket, None)
            if entry is None:
                return False
            session, expires = entry
            return current < expires and self.session_valid(session)

    def _prune(self, now: float) -> None:
        for key, (_, expires) in list(self._tickets.items()):
            if now >= expires:
                self._tickets.pop(key, None)
