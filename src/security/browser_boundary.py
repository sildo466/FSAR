# SPDX-License-Identifier: MIT
"""The browser-side checks that guard the dashboard's own endpoints.

These answer "did a page the user opened send this", never "who is the user".
A caller writes its own Host, Origin and Fetch-Metadata headers, so none of
them can be an identity — what this still buys is the cross-origin boundary:
a page on another site cannot make the browser issue a same-origin request.
The socket peer is the part a caller does not control, and that check lives
with the endpoints.

The two credential-header parsers below live here too: both are shared by the
GUI and the room API, and both only read what a caller sent — they decide
nothing.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Iterable

DEFAULT_ORIGINS = {
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}
DEFAULT_HOSTS = {"127.0.0.1:8765", "localhost:8765"}


class BrowserBoundary:
    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def request_allowed(
        self,
        *,
        host: str,
        origin: str | None = None,
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
