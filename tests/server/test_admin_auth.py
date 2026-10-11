# SPDX-License-Identifier: MIT
from __future__ import annotations

from fastapi.testclient import TestClient

import src.server.ws_server as ws_mod

ORIGIN = {"origin": "http://127.0.0.1:8765"}
BASE = dict(
    base_url="https://127.0.0.1:8765", cookies={}, headers=ORIGIN,
    client=("127.0.0.1", 40000),
)


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
    local = TestClient(ws_mod.app, **BASE)
    assert local.post("/api/auth/bootstrap", json={"token": "nope"}).status_code == 403

    remote = TestClient(
        ws_mod.app, base_url="https://127.0.0.1:8765", cookies={},
        client=("203.0.113.7", 40000),
    )
    assert remote.post("/api/auth/bootstrap", json={"token": "nope"}).status_code == 403
