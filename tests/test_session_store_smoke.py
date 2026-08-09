"""Smoke test for SessionStore — exercises CRUD + cascade + ordering."""

import os
import tempfile
import time
from pathlib import Path

from src.memory.session_store import SessionStore, MessageRow


def _store() -> SessionStore:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return SessionStore(Path(tmp.name))


def _cleanup(path: Path) -> None:
    for _ in range(5):
        try:
            os.unlink(path)
            return
        except PermissionError:
            time.sleep(0.05)


def test_create_returns_uuid():
    s = _store()
    row = s.create()
    assert row.id and len(row.id) >= 16
    assert row.message_count == 0
    assert row.title == ""
    assert row.pinned is False
    s.delete(row.id)
    _cleanup(s._db_path)


def test_list_orders_pinned_first_then_updated():
    s = _store()
    a = s.create()
    b = s.create()
    s.set_pinned(b.id, True)
    rows = s.list()
    assert rows[0].id == b.id, "pinned should sort first"
    assert rows[1].id == a.id
    s.delete(a.id)
    s.delete(b.id)
    _cleanup(s._db_path)


def test_rename_and_pin():
    s = _store()
    r = s.create()
    assert s.rename(r.id, "Hello world")
    assert s.get(r.id).title == "Hello world"
    s.set_pinned(r.id, True)
    assert s.get(r.id).pinned is True
    s.delete(r.id)
    _cleanup(s._db_path)


def test_delete_cascades_messages():
    s = _store()
    r = s.create()
    s.append_message(r.id, "user", "hi")
    s.append_message(r.id, "assistant", "hello")
    assert s.get(r.id).message_count == 2
    s.delete(r.id)
    assert s.get(r.id) is None
    msgs = s.get_session_messages(r.id)
    assert msgs == []
    _cleanup(s._db_path)


def test_append_message_unknown_conv_returns_none():
    s = _store()
    assert s.append_message("nope", "user", "x") is None
    _cleanup(s._db_path)


def test_recent_messages_ordering():
    s = _store()
    r = s.create()
    for i in range(5):
        s.append_message(r.id, "user", f"m{i}")
    recent = s.get_recent_messages(r.id, limit=3)
    assert [m.content for m in recent] == ["m2", "m3", "m4"]
    s.delete(r.id)
    _cleanup(s._db_path)


if __name__ == "__main__":
    test_create_returns_uuid()
    test_list_orders_pinned_first_then_updated()
    test_rename_and_pin()
    test_delete_cascades_messages()
    test_append_message_unknown_conv_returns_none()
    test_recent_messages_ordering()
    print("all SessionStore smoke tests passed")