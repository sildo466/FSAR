# SPDX-License-Identifier: MIT
"""Exact-title session cleanup.

Run against the live store with `python -m src.utils.cleanup_sessions`
(dry-run) and `python -m src.utils.cleanup_sessions --apply` to delete.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from src.memory.session_store import SessionRow, SessionStore
from src.utils.fsar_config import FsarConfig
from src.utils.fsar_home import get_fsar_home

TITLE = "delete it"


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


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    config = FsarConfig(get_fsar_home() / "config" / "fsar.yaml")
    db = Path(config.memory_sqlite_path)
    if not db.is_file():
        print(f"session store not found: {db}")
        return 1
    print(f"database: {db}")
    targets = find_sessions_by_title(SessionStore(db), TITLE)
    print(f"title == {TITLE!r}: {len(targets)} row(s)")
    for row in targets:
        print(f"  {row.id}  messages={row.message_count}  pinned={row.pinned}")
    count, backup = cleanup(db, TITLE, apply=apply)
    if not apply:
        print("dry-run; re-run with --apply to delete")
        return 0
    print(f"backup: {backup}")
    print(f"deleted: {count}")
    remaining = len(find_sessions_by_title(SessionStore(db), TITLE))
    print(f"remaining: {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
