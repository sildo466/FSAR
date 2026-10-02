"""Small SQLite helpers shared by integration tests and callers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.utils.fsar_config import get_default_config


def db_path() -> Path:
    return Path(get_default_config().memory_sqlite_path)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def enable_wal(path: str | Path | None = None) -> None:
    """Put a database in WAL mode.

    Journal mode is a property of the file, so one call covers every store
    that opens it afterwards. The room API runs its own event loop in a second
    thread and still does its reads and writes synchronously on that loop; in
    the default rollback mode a reader waits behind any in-flight commit, and
    those waits were long enough to stall the loop and refuse connections. WAL
    lets readers and the writer proceed at the same time.
    """
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    finally:
        conn.close()


__all__ = ["db_path", "connect", "transaction", "enable_wal"]
