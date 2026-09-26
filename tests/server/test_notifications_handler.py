# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from src.notifications.store import NotificationStore
from src.server.handlers import notifications as handler


class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload):
        self.sent.append(payload)


class _FakeConfig:
    def __init__(self, db_path):
        self._db = str(db_path)

    def get(self, key, default=None):
        if key == "memory.sqlite_path":
            return self._db
        if key == "notifications.release.enabled":
            return True
        if key == "notifications.release.include_prerelease":
            return False
        if key == "notifications.announcement.enabled":
            return True
        if key == "notifications.review.enabled":
            return True
        return default


@pytest.fixture
def config(tmp_path):
    return _FakeConfig(tmp_path / "m.db")


async def test_list_returns_items_and_unread(config):
    NotificationStore(config.get("memory.sqlite_path")).add(
        kind="release", title="FSAR v0.7.0", ref="v0.7.0"
    )
    ws = _FakeWS()
    assert await handler.dispatch(ws, {"type": "notifications.list"}, config) is True
    payload = ws.sent[0]
    assert payload["type"] == "notifications.list_result"
    assert len(payload["items"]) == 1
    assert payload["unread"] == 1
    assert payload["kinds"] == ["review", "release", "announcement"]
    assert payload["settings"]["release"]["include_prerelease"] is False


async def test_mark_read_clears_unread(config):
    store = NotificationStore(config.get("memory.sqlite_path"))
    first = store.add(kind="review", title="r", ref="1")
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "notifications.mark_read", "ids": [first]}, config)
    assert ws.sent[0] == {
        "type": "notifications.read_result",
        "unread": 0,
        "ids": [first],
        "cleared": False,
    }


async def test_mark_read_reports_only_the_ids_it_changed(config):
    """Expanding one item must not silently clear the rest of the feed."""
    store = NotificationStore(config.get("memory.sqlite_path"))
    first = store.add(kind="review", title="r", ref="1")
    store.add(kind="review", title="r2", ref="2")
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "notifications.mark_read", "ids": [first]}, config)
    payload = ws.sent[0]
    assert payload["ids"] == [first]
    assert payload["unread"] == 1


async def test_mark_read_without_ids_marks_everything(config):
    store = NotificationStore(config.get("memory.sqlite_path"))
    first = store.add(kind="review", title="r", ref="1")
    second = store.add(kind="review", title="r2", ref="2")
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "notifications.mark_read"}, config)
    assert ws.sent[0]["unread"] == 0
    assert sorted(ws.sent[0]["ids"]) == sorted([first, second])


async def test_clear_empties_the_feed(config):
    store = NotificationStore(config.get("memory.sqlite_path"))
    store.add(kind="review", title="r", ref="1")
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "notifications.clear"}, config)
    assert ws.sent[0] == {
        "type": "notifications.read_result",
        "unread": 0,
        "ids": [],
        "cleared": True,
    }
    assert store.list() == []


async def test_unknown_message_is_not_handled(config):
    ws = _FakeWS()
    assert await handler.dispatch(ws, {"type": "notifications.nope"}, config) is False
    assert ws.sent == []
