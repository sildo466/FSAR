# SPDX-License-Identifier: MIT
"""The shared database is opened in WAL mode.

The room API runs its own event loop in a second thread and reads and writes the
same file the GUI thread is committing to. In the default rollback mode a reader
waits behind any in-flight commit, and a loop that waits is a refused
connection.
"""

from __future__ import annotations

import sqlite3

from src.memory.db import enable_wal


def _journal_mode(path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    finally:
        conn.close()


def test_enable_wal_switches_the_journal_mode(tmp_path) -> None:
    db = tmp_path / "shared.db"
    enable_wal(db)
    assert _journal_mode(db) == "wal"


def test_the_mode_belongs_to_the_file_not_the_connection(tmp_path) -> None:
    """Journal mode is stored in the file, so every store that opens the shared
    database afterwards gets it without being changed itself."""
    db = tmp_path / "shared.db"
    enable_wal(db)
    # A fresh connection, opened the way a store opens one.
    assert _journal_mode(db) == "wal"


def test_enable_wal_makes_the_directory_it_needs(tmp_path) -> None:
    db = tmp_path / "nested" / "shared.db"
    enable_wal(db)
    assert db.exists()
