# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _send(ws, msg):
    ws.send_json(msg)
    for _ in range(20):
        out = ws.receive_json()
        if str(out.get("type", "")).startswith("content_guard."):
            return out
    raise AssertionError(f"no content_guard.* reply to {msg['type']}")


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    import src.server.ws_server as ws_mod
    from src.security.content_guard import ContentGuard
    from src.security.content_screen import ScreenVerdict

    class _Cfg:
        def get(self, path, default=None):
            if path == "security.content_screening.enabled":
                return True
            if path == "security.content_screening.threshold":
                return 0.5
            return default

        def get_judge(self):
            return {}

        def get_active_provider(self):
            return {}

    g = ContentGuard(_Cfg(), db_path=tmp_path / "m.db", autostart=False)
    g.record(
        "chunk", "5", "bad payload", kind="memory_chunk", verdict=ScreenVerdict(False, 0.9)
    )
    g.set_report({"scanned": 12, "quarantined": 1, "unavailable": 2, "total": 12})
    monkeypatch.setattr(ws_mod, "_get_content_guard", lambda: g)
    return g, ws_mod


def test_list_returns_items_whitelist_and_report(seeded):
    guard, ws_mod = seeded
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        out = _send(ws, {"type": "content_guard.list"})
    assert out["type"] == "content_guard.list_result"
    assert len(out["items"]) == 1
    assert out["items"][0]["text"] == "bad payload"
    assert out["report"]["unavailable"] == 2
    assert "chunk" in out["stores"]
    assert out["enabled"] is True


def test_purge_removes_item(seeded):
    guard, ws_mod = seeded
    qid = guard.list_quarantine()[0]["id"]
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        out = _send(ws, {"type": "content_guard.purge", "id": qid})
        assert out["ok"] is True
        assert _send(ws, {"type": "content_guard.list"})["items"] == []


def test_unwhitelist_removes_hash(seeded):
    guard, ws_mod = seeded
    guard.add_to_whitelist("hello", added_by="restore")
    sha = guard.digest("hello")
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        out = _send(ws, {"type": "content_guard.unwhitelist", "sha256": sha})
    assert out["ok"] is True
    assert guard.is_whitelisted("hello") is False


def test_unknown_id_is_not_ok(seeded):
    guard, ws_mod = seeded
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        out = _send(ws, {"type": "content_guard.purge", "id": 99999})
    assert out["ok"] is False
