# SPDX-License-Identifier: MIT
"""The LAN app's surface: what exists, and what it says when it refuses."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.memory.auth_audit import AuthAuditStore
from src.memory.lan_blocklist import LanBlocklist
from src.memory.member_tokens import MemberTokenStore
from src.security.rate_budget import RateBudget
from src.server.room_app import RoomDeps, create_room_app


@pytest.fixture()
def deps(tmp_path: Path) -> RoomDeps:
    db = tmp_path / "lan.db"
    return RoomDeps(
        tokens=MemberTokenStore(db),
        blocklist=LanBlocklist(db),
        audit=AuthAuditStore(db),
        rooms=None,
        members=None,
        budget=RateBudget(),
    )


@pytest.fixture()
def client(deps: RoomDeps) -> TestClient:
    return TestClient(create_room_app(deps))


def test_docs_redoc_and_openapi_are_absent(client: TestClient) -> None:
    """A scanner must not be handed a route inventory."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_an_unknown_path_404s_in_the_uniform_shape(client: TestClient) -> None:
    response = client.get("/room/whatever")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "request_id"}
    assert body["code"] == "not_found"
    assert body["request_id"]


def test_an_unmatched_method_is_a_uniform_404_too(client: TestClient) -> None:
    response = client.post("/room/whatever")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_every_response_carries_no_store(client: TestClient) -> None:
    assert client.get("/room/whatever").headers["cache-control"] == "no-store"


def test_every_response_carries_a_fresh_request_id(client: TestClient) -> None:
    first = client.get("/room/whatever")
    second = client.get("/room/whatever")
    assert first.headers["x-request-id"]
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert first.json()["request_id"] == first.headers["x-request-id"]


def test_the_error_body_never_leaks_internals(client: TestClient) -> None:
    text = client.get("/room/whatever").text
    for leak in ("Traceback", "sqlite", "SELECT", "room_member_tokens", "C:\\"):
        assert leak not in text


def test_the_app_does_not_advertise_itself(client: TestClient) -> None:
    assert "FastAPI" not in client.get("/room/whatever").headers.get("server", "")


def test_each_factory_call_builds_its_own_app(deps: RoomDeps) -> None:
    """Independence matters: the isolation tests build several at once."""
    assert create_room_app(deps) is not create_room_app(deps)
