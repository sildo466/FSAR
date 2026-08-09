"""Create PL2.7 social bridge tables and session source columns."""

from __future__ import annotations

import sqlite3

NAME = "2026_07_17_pl2_7_social"

_SESSION_COLUMNS = (
    ("source_platform", "TEXT"),
    ("source_peer_id", "TEXT"),
    ("source_meta_json", "TEXT"),
)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(
        row[1] == column
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _ensure_session_columns(conn: sqlite3.Connection) -> None:
    for name, declaration in _SESSION_COLUMNS:
        if not _column_exists(conn, "sessions", name):
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {declaration}")


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS social_bindings (
            platform          TEXT NOT NULL,
            peer_id           TEXT NOT NULL,
            fsar_user_card_id INTEGER NOT NULL DEFAULT 1,
            display_name      TEXT,
            bound_at          TEXT NOT NULL,
            last_seen_at      TEXT NOT NULL,
            muted             INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(platform, peer_id),
            FOREIGN KEY(fsar_user_card_id)
                REFERENCES user_cards(id) ON DELETE RESTRICT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS social_state (
            platform   TEXT PRIMARY KEY,
            state_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_session_source
        ON sessions(source_platform, source_peer_id)
        WHERE source_platform IS NOT NULL AND source_peer_id IS NOT NULL
        """
    )


def run(conn: sqlite3.Connection) -> None:
    _ensure_session_columns(conn)
    _ensure_tables(conn)
    conn.commit()


if __name__ == "__main__":
    import sys

    from src.memory.db import connect

    connection = connect()
    try:
        run(connection)
    finally:
        connection.close()
    print("migration applied", file=sys.stderr)
