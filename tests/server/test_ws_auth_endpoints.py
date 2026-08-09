from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import src.server.ws_server as ws_mod


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "host": "127.0.0.1:8765",
        "origin": "http://127.0.0.1:8765",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers


def test_yaml_endpoint_requires_token():
    client = TestClient(ws_mod.app)

    assert client.get("/api/fsar_yaml", headers=_headers()).status_code == 401
    response = client.get(
        "/api/fsar_yaml", headers=_headers(ws_mod._ws_auth.ensure_token())
    )
    assert response.status_code == 200


def test_ws_rejects_missing_token():
    client = TestClient(ws_mod.app)

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            "/ws",
            headers=_headers(),
            subprotocols=["fsar-v1", "wrong"],
        ):
            pass

    assert error.value.code == 1008
