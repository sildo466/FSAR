"""SQLite migrations used by the integration subsystem."""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path


def run_pending(db_path: str | Path = "data/memory.db") -> None:
    """Apply all bundled migrations to ``db_path``.

    Migrations are idempotent and the project historically had no migration
    registry, so running the small set on startup is safe.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        migration = importlib.import_module(
            "data.migrations.2026_07_16_pl2_6_integration_tables"
        )
        migration.up(conn)


__all__ = ["run_pending"]
