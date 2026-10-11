# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import src.server.ws_server as ws_mod

ORIGIN = {"origin": "http://127.0.0.1:8765"}
BASE = dict(
    base_url="https://127.0.0.1:8765", cookies={}, headers=ORIGIN,
    client=("127.0.0.1", 40000),
)


def _client(**over) -> TestClient:
    """An anonymous GUI client, loopback unless the test says otherwise."""
    kwargs = dict(BASE)
    kwargs.update(over)
    return TestClient(ws_mod.app, **kwargs)


def _with_session(session: str, **over) -> TestClient:
    return _client(cookies={"fsar_admin": session}, **over)


def test_bootstrap_sets_the_session_cookie_and_is_single_use():
    token = ws_mod._admin_sessions.rotate_bootstrap()
    client = TestClient(ws_mod.app, **BASE)

    first = client.post("/api/auth/bootstrap", json={"token": token})
    assert first.status_code == 200
    assert first.cookies.get("fsar_admin")

    # A second browser (fresh jar) replaying the same token must be refused.
    replay = TestClient(ws_mod.app, **BASE)
    assert replay.post("/api/auth/bootstrap", json={"token": token}).status_code == 403


def test_bootstrap_refuses_a_wrong_token_and_a_foreign_peer():
    ws_mod._admin_sessions.rotate_bootstrap()
    assert _client().post("/api/auth/bootstrap", json={"token": "nope"}).status_code == 403
    assert _client(client=("203.0.113.7", 40000)).post(
        "/api/auth/bootstrap", json={"token": "nope"}
    ).status_code == 403


def test_ws_ticket_needs_a_session():
    assert _client().get("/api/auth/ws-ticket").status_code == 401

    session = ws_mod._admin_sessions.create_session()
    assert _with_session(session).get("/api/auth/ws-ticket").status_code == 200


def _connect(ticket: str, peer: str = "127.0.0.1"):
    return _client(client=(peer, 40000)).websocket_connect(
        "/ws", subprotocols=["fsar-v1", ticket],
    )


def test_a_ticket_opens_the_socket_once_and_only_from_this_machine():
    session = ws_mod._admin_sessions.create_session()
    ticket = ws_mod._admin_sessions.issue_ticket(session)

    with _connect(ticket) as ws:
        assert ws.receive_json()["type"] == "snapshot"

    # The same ticket again: already spent.
    with pytest.raises(WebSocketDisconnect):
        with _connect(ticket):
            pass

    # A live ticket from somewhere else is refused, and the refusal must not
    # burn the ticket on its way out.
    elsewhere = ws_mod._admin_sessions.issue_ticket(session)
    with pytest.raises(WebSocketDisconnect):
        with _connect(elsewhere, "203.0.113.7"):
            pass
    with _connect(elsewhere) as ws:
        assert ws.receive_json()["type"] == "snapshot"


def test_the_old_long_lived_token_is_not_a_credential():
    with pytest.raises(WebSocketDisconnect) as error:
        with _connect("anything"):
            pass
    assert error.value.code == 1008


@pytest.mark.parametrize("method,path", [
    ("get", "/api/fsar_yaml"),
    ("get", "/api/models"),
    ("get", "/api/models/hiyori/hiyori.model3.json"),
    ("get", "/api/card/1/avatar"),
    ("get", "/skin-assets/warm/bg.png"),
    ("get", "/api/social/status"),
    ("post", "/api/social/wechat/qr"),
    ("get", "/api/scheduler/jobs"),
    ("get", "/api/scheduler/runs"),
    ("get", "/api/scheduler/handlers"),
    ("get", "/api/scheduler/system-jobs"),
    ("post", "/api/scheduler/jobs"),
])
def test_every_management_endpoint_refuses_an_anonymous_caller(method, path):
    call = getattr(_client(), method)
    response = call(path, json={}) if method == "post" else call(path)
    assert response.status_code in (401, 403), (
        f"{method.upper()} {path} answered {response.status_code} without a session"
    )


def test_a_foreign_peer_is_refused_even_with_a_valid_session():
    session = ws_mod._admin_sessions.create_session()
    remote = _with_session(session, client=("203.0.113.7", 40000))
    assert remote.get("/api/fsar_yaml").status_code == 403


def test_health_needs_no_session():
    assert _client().get("/health").status_code == 200


def test_a_failed_handshake_never_logs_the_ticket():
    from src.utils.logger import logger

    lines: list[str] = []
    sink_id = logger.add(lambda m: lines.append(m), level="WARNING")
    try:
        session = ws_mod._admin_sessions.create_session()
        spent = ws_mod._admin_sessions.issue_ticket(session)
        ws_mod._admin_sessions.consume_ticket(spent)

        with pytest.raises(WebSocketDisconnect):
            with _connect(spent):
                pass
    finally:
        logger.remove(sink_id)

    text = "".join(lines)
    assert "ws /ws rejected" in text, "the refusal never reached the log"
    assert spent not in text
    assert "fsar-v1" not in text
