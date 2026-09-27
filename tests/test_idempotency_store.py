# SPDX-License-Identifier: MIT
"""De-duplication for retried LAN requests."""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from src.memory.idempotency import IdempotencyStore


def _store(ttl: float = 60.0) -> IdempotencyStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return IdempotencyStore(Path(tmp.name) / "idem.db", ttl_seconds=ttl)


def _age(store: IdempotencyStore, seconds: float) -> None:
    """Backdate the rows, which is what actually happens over time."""
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE lan_idempotency SET created_at = created_at - ?", (seconds,),
        )
        conn.commit()


def test_a_fresh_key_is_new() -> None:
    assert _store().lookup("s", "k", "hash") == ("new", None)


def test_a_repeat_with_the_same_body_replays() -> None:
    store = _store()
    store.remember("s", "k", "hash", 200, {"row_id": 7})
    assert store.lookup("s", "k", "hash") == ("replay", {"row_id": 7})


def test_a_repeat_with_a_different_body_conflicts() -> None:
    store = _store()
    store.remember("s", "k", "hash", 200, {"row_id": 7})
    assert store.lookup("s", "k", "other-hash") == ("conflict", None)


def test_scope_separates_keys() -> None:
    store = _store()
    store.remember("room-1:member-a", "k", "hash", 200, {"row_id": 1})
    assert store.lookup("room-1:member-b", "k", "hash") == ("new", None)


def test_remember_is_idempotent() -> None:
    store = _store()
    store.remember("s", "k", "hash", 200, {"row_id": 7})
    store.remember("s", "k", "hash", 200, {"row_id": 7})
    assert store.lookup("s", "k", "hash") == ("replay", {"row_id": 7})


def test_an_expired_key_is_new_again() -> None:
    store = _store(ttl=1.0)
    store.remember("s", "k", "hash", 200, {"row_id": 7})
    _age(store, 10.0)
    assert store.lookup("s", "k", "hash") == ("new", None)


def test_lookup_can_be_asked_about_a_later_moment() -> None:
    store = _store(ttl=1.0)
    store.remember("s", "k", "hash", 200, {"row_id": 7})
    assert store.lookup("s", "k", "hash", now=time.time() + 1000) == ("new", None)
    assert store.lookup("s", "k", "hash", now=time.time()) == (
        "replay", {"row_id": 7},
    )


def test_purge_drops_expired_rows_and_reports_how_many() -> None:
    store = _store(ttl=1.0)
    store.remember("s", "a", "h", 200, {"row_id": 1})
    store.remember("s", "b", "h", 200, {"row_id": 2})
    _age(store, 10.0)
    assert store.purge_expired() == 2
    assert store.lookup("s", "a", "h") == ("new", None)


def test_purge_keeps_unexpired_rows() -> None:
    store = _store(ttl=3600.0)
    store.remember("s", "a", "h", 200, {"row_id": 1})
    assert store.purge_expired() == 0
    assert store.lookup("s", "a", "h") == ("replay", {"row_id": 1})


def test_a_non_ascii_body_still_replays() -> None:
    store = _store()
    store.remember("s", "k", "hash", 200, {"row_id": 3, "note": "日本語"})
    assert store.lookup("s", "k", "hash") == ("replay", {"row_id": 3, "note": "日本語"})


def test_a_corrupt_body_is_treated_as_new() -> None:
    """Better to re-answer than to replay something unreadable."""
    store = _store()
    store.remember("s", "k", "hash", 200, {"row_id": 1})
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE lan_idempotency SET body = ?", ("{not json",))
        conn.commit()
    assert store.lookup("s", "k", "hash") == ("new", None)
