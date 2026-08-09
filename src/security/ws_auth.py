from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable

from src.skills.atomic import atomic_write_text
from src.utils.fsar_home import get_fsar_home


DEFAULT_ORIGINS = {
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}
DEFAULT_HOSTS = {"127.0.0.1:8765", "localhost:8765"}


class WSAuthenticator:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_fsar_home() / "security" / "ws_token"
        self._token = ""
        self._lock = threading.RLock()
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def rotate(self) -> str:
        with self._lock:
            self._token = secrets.token_urlsafe(48)
            atomic_write_text(self.path, self._token + "\n", mode=0o600)
            self._failures.clear()
            return self._token

    def ensure_token(self) -> str:
        with self._lock:
            return self._token or self.rotate()

    def verify_token(self, candidate: str) -> bool:
        token = self.ensure_token()
        return bool(candidate) and hmac.compare_digest(token, candidate)

    def request_allowed(
        self,
        *,
        host: str,
        origin: str | None,
        allowed_origins: Iterable[str] = (),
        fetch_site: str | None = None,
        referer: str | None = None,
    ) -> bool:
        origins = DEFAULT_ORIGINS | {item.rstrip("/") for item in allowed_origins}
        hosts = DEFAULT_HOSTS | {
            item.split("://", 1)[-1].rstrip("/") for item in origins
        }
        normalized_host = host.lower()
        if normalized_host not in {item.lower() for item in hosts}:
            return False
        if origin:
            return origin.rstrip("/").lower() in {item.lower() for item in origins}
        if fetch_site and fetch_site.lower() != "same-origin":
            return False
        if referer:
            return any(referer.lower().startswith(item.lower() + "/") for item in origins)
        return fetch_site == "same-origin"

    def is_rate_limited(self, client_id: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        failures = self._failures[client_id]
        while failures and current - failures[0] > 60:
            failures.popleft()
        return len(failures) >= 3

    def record_failure(self, client_id: str, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        failures = self._failures[client_id]
        failures.append(current)
        while failures and current - failures[0] > 60:
            failures.popleft()


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def websocket_token(protocol_header: str | None) -> str:
    protocols = [item.strip() for item in (protocol_header or "").split(",")]
    if len(protocols) < 2 or protocols[0] != "fsar-v1":
        return ""
    return protocols[1]

