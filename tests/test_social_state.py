from __future__ import annotations

import importlib
import sqlite3

import pytest

from src.social.state import (
    append_session_message,
    is_muted,
    load_cursor,
    load_or_create_session,
    load_session_messages,
    save_cursor,
    touch_binding,
    upsert_binding,
)


migration = importlib.import_module("data.migrations.2026_07_17_pl2_7_social")


def test_migration_adds_columns_and_tables():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            pinned INTEGER,
            created_at TEXT,
            updated_at TEXT,
            message_count INTEGER
        )
        """
    )
    conn.execute("CREATE TABLE user_cards (id INTEGER PRIMARY KEY)")

    migration.run(conn)
    migration.run(conn)

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    assert {"source_platform", "source_peer_id", "source_meta_json"} <= columns
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"social_bindings", "social_state"} <= tables


@pytest.fixture
def social_db(tmp_path, monkeypatch):
    path = tmp_path / "social.db"
    connection = sqlite3.connect(str(path))
    connection.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            pinned INTEGER,
            created_at TEXT,
            updated_at TEXT,
            message_count INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            session_fk TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE TABLE user_cards (id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO user_cards(id) VALUES (1)")
    migration.run(connection)
    connection.close()
    monkeypatch.setattr("src.social.state.db_path", lambda: path)
    return path


def test_binding_upsert_and_mute(social_db):
    upsert_binding("telegram", "42", display_name="alice")
    touch_binding("telegram", "42")
    assert is_muted("telegram", "42") is False

    with sqlite3.connect(str(social_db)) as connection:
        connection.execute(
            "UPDATE social_bindings SET muted=1 "
            "WHERE platform='telegram' AND peer_id='42'"
        )
        connection.commit()

    assert is_muted("telegram", "42") is True


def test_cursor_round_trip(social_db):
    save_cursor("telegram", {"offset": 12345})
    assert load_cursor("telegram") == {"offset": 12345}


def test_social_peer_reuses_session(social_db):
    first = load_or_create_session("telegram", "42")
    second = load_or_create_session("telegram", "42")
    other = load_or_create_session("telegram", "43")

    assert first == second
    assert other != first


def test_session_message_round_trip_updates_count(social_db):
    session_id = load_or_create_session("telegram", "42")

    append_session_message(session_id, "user", "hello")
    append_session_message(session_id, "assistant", "hi")

    assert load_session_messages(session_id) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    with sqlite3.connect(str(social_db)) as connection:
        count = connection.execute(
            "SELECT message_count FROM sessions WHERE id=?", (session_id,)
        ).fetchone()[0]
    assert count == 2
