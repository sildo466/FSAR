# SPDX-License-Identifier: MIT
"""One-shot session cleanup, used by scripts/cleanup_test_sessions.py."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from src.memory.session_store import SessionRow, SessionStore


def find_sessions_by_title(store: SessionStore, title: str) -> list[SessionRow]:
    """Sessions whose title equals `title` after trim, case-insensitively.

    Exact match only: a substring rule would sweep up conversations the user
    actually named, e.g. "please delete it now".
    """
    wanted = title.strip().lower()
    rows = store.list(limit=10_000, kind=None)
    return [row for row in rows if row.title.strip().lower() == wanted]


def cleanup(db_path: Path, title: str, *, apply: bool) -> tuple[int, Path | None]:
    """Delete matching sessions. Returns (count, backup_path).

    Backs up the whole database before the first delete, so a mistaken pattern
    is recoverable without relying on SQLite's journal.
    """
    store = SessionStore(db_path)
    targets = find_sessions_by_title(store, title)
    if not targets:
        return 0, None
    if not apply:
        return len(targets), None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    shutil.copy2(db_path, backup)
    for row in targets:
        store.delete(row.id)
    return len(targets), backup
