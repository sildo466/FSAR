# SPDX-License-Identifier: MIT
"""Session cleanup utility.

Two selectors, both dry-run by default:

    python -m src.utils.cleanup_sessions                 # title == "delete it"
    python -m src.utils.cleanup_sessions --empty         # zero-message chats

Add `--apply` to delete. The whole database is copied first.
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


def find_empty_sessions(store: SessionStore) -> list[SessionRow]:
    """Chat sessions with no messages and no pin.

    Mirrors `conversation.prune_empty_sessions`. A cancelled turn persists no
    messages, yet the title generator has already named the session from the
    user's input, so "titled but empty" shells linger.
    """
    rows = store.list(limit=10_000)
    return [row for row in rows if row.message_count == 0 and not row.pinned]


def _purge(
    db_path: Path, targets: list[SessionRow], *, apply: bool
) -> tuple[int, Path | None]:
    """Delete the given sessions. Returns (count, backup_path).

    Backs up the whole database before the first delete, so a mistaken selector
    is recoverable without relying on SQLite's journal.
    """
    if not targets:
        return 0, None
    if not apply:
        return len(targets), None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    shutil.copy2(db_path, backup)
    store = SessionStore(db_path)
    for row in targets:
        store.delete(row.id)
    return len(targets), backup


def cleanup(db_path: Path, title: str, *, apply: bool) -> tuple[int, Path | None]:
    """Delete sessions matching `title` exactly. Returns (count, backup_path)."""
    targets = find_sessions_by_title(SessionStore(db_path), title)
    return _purge(db_path, targets, apply=apply)


def cleanup_empty(db_path: Path, *, apply: bool) -> tuple[int, Path | None]:
    """Delete zero-message unpinned chats. Returns (count, backup_path)."""
    targets = find_empty_sessions(SessionStore(db_path))
    return _purge(db_path, targets, apply=apply)


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    sweep_empty = "--empty" in argv

    config = FsarConfig(get_fsar_home() / "config" / "fsar.yaml")
    db = Path(config.memory_sqlite_path)
    if not db.is_file():
        print(f"session store not found: {db}")
        return 1
    print(f"database: {db}")

    if sweep_empty:
        label = "zero-message unpinned chats"
        targets = find_empty_sessions(SessionStore(db))
    else:
        label = f"title == {TITLE!r}"
        targets = find_sessions_by_title(SessionStore(db), TITLE)

    print(f"{label}: {len(targets)} row(s)")
    for row in targets:
        print(
            f"  {row.id}  title={row.title!r}  "
            f"messages={row.message_count}  pinned={row.pinned}"
        )

    if sweep_empty:
        count, backup = cleanup_empty(db, apply=apply)
    else:
        count, backup = cleanup(db, TITLE, apply=apply)

    if not apply:
        print("dry-run; re-run with --apply to delete")
        return 0
    print(f"backup: {backup}")
    print(f"deleted: {count}")

    remaining = (
        len(find_empty_sessions(SessionStore(db)))
        if sweep_empty
        else len(find_sessions_by_title(SessionStore(db), TITLE))
    )
    print(f"remaining: {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
