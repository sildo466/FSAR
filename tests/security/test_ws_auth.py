from __future__ import annotations

from src.security.ws_auth import WSAuthenticator, bearer_token, websocket_token


def test_ws_token_rotates_and_is_persisted(tmp_path):
    auth = WSAuthenticator(tmp_path / "security" / "ws_token")

    first = auth.rotate()
    second = auth.rotate()

    assert first != second
    assert auth.path.read_text(encoding="utf-8").strip() == second
    assert len(second) == 64


def test_origin_host_and_protocol_validation(tmp_path):
    auth = WSAuthenticator(tmp_path / "token")
    token = auth.rotate()

    assert auth.request_allowed(
        host="127.0.0.1:8765", origin="http://127.0.0.1:8765"
    )
    assert not auth.request_allowed(
        host="evil.example", origin="http://127.0.0.1:8765"
    )
    assert websocket_token(f"fsar-v1, {token}") == token
    assert bearer_token(f"Bearer {token}") == token


def test_three_failures_rate_limit_for_sixty_seconds(tmp_path):
    auth = WSAuthenticator(tmp_path / "token")
    for instant in (1.0, 2.0, 3.0):
        auth.record_failure("client", now=instant)

    assert auth.is_rate_limited("client", now=10.0)
    assert not auth.is_rate_limited("client", now=64.0)
