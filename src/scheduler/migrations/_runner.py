"""Tiny migration runner — reads SQL files from this directory and applies them."""
from __future__ import annotations

import sqlite3
from pathlib import Path


_MIGRATIONS_DIR = Path(__file__).parent


def apply_sql(db_path: Path, sql_filename: str) -> None:
    sql_file = _MIGRATIONS_DIR / sql_filename
    if not sql_file.exists():
        return
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()