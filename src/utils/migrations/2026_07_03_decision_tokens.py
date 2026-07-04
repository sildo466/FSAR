# SPDX-License-Identifier: Apache-2.0
"""Add token columns to decision_log."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def apply(db_path: str | Path) -> None:
    p = Path(db_path)
    if not p.exists():
        return
    with sqlite3.connect(str(p)) as conn:
        cur = conn.execute("PRAGMA table_info(decision_log)")
        cols = {row[1] for row in cur.fetchall()}
        for ddl, name in [
            ("ALTER TABLE decision_log ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0", "prompt_tokens"),
            ("ALTER TABLE decision_log ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0", "completion_tokens"),
            ("ALTER TABLE decision_log ADD COLUMN cached_tokens INTEGER NOT NULL DEFAULT 0", "cached_tokens"),
        ]:
            if name not in cols:
                conn.execute(ddl)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_provider_created "
            "ON decision_log(chosen_tool, created_at)"
        )
        conn.commit()


if __name__ == "__main__":
    import sys
    apply(sys.argv[1] if len(sys.argv) > 1 else "data/memory.db")
