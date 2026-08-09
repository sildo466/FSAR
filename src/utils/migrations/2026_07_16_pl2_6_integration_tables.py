"""Apply PL2.6 integration tables to an existing FSAR database."""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path


def apply(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    migration = importlib.import_module(
        "data.migrations.2026_07_16_pl2_6_integration_tables"
    )
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        migration.up(conn)


if __name__ == "__main__":
    import sys

    apply(sys.argv[1] if len(sys.argv) > 1 else "data/memory.db")
