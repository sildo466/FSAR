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


__all__ = ["db_path", "connect", "transaction"]
