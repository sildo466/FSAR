# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.security.browser_boundary import BrowserBoundary, websocket_token


def test_origin_host_and_protocol_validation():
    boundary = BrowserBoundary()

    assert boundary.request_allowed(
        host="127.0.0.1:8765", origin="http://127.0.0.1:8765"
    )
    assert not boundary.request_allowed(
        host="evil.example", origin="http://127.0.0.1:8765"
    )
    assert boundary.request_allowed(host="127.0.0.1:8765", fetch_site="same-origin")
    assert not boundary.request_allowed(
        host="127.0.0.1:8765", fetch_site="cross-site"
    )
    assert websocket_token("fsar-v1, t") == "t"
    assert websocket_token("t") == ""
    assert websocket_token(None) == ""


def test_three_failures_rate_limit_for_sixty_seconds():
    boundary = BrowserBoundary()
    for instant in (1.0, 2.0, 3.0):
        boundary.record_failure("client", now=instant)

    assert boundary.is_rate_limited("client", now=10.0)
    assert not boundary.is_rate_limited("client", now=64.0)
