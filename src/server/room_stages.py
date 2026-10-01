# SPDX-License-Identifier: MIT
"""One git worktree per member.

A worktree shares the project's object store, so a member's git commands land
under <project>/.git/worktrees/. That is the price of this shape and it is
acceptable in P3 only because the workers are character cards A runs itself
under WorkspaceGate. P4, which lets external members work, must revisit it.

Every git call here runs with the repository's own configuration ignored: a
member that can write its staging can write config that git would otherwise
execute.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.memory.workspace import Workspace, WorkspaceRepo
from src.utils.fsar_home import get_fsar_home

GIT_SAFE = ("-c", "core.hooksPath=", "-c", "core.fsmonitor=false")


class StageError(RuntimeError):
    pass


def stage_root() -> Path:
    return get_fsar_home() / "staging"


def stage_path(room_id: int, kind: str, ref: str) -> Path:
    return stage_root() / f"room-{int(room_id)}" / f"{kind}-{ref}"


def branch_for(room_id: int, kind: str, ref: str) -> str:
    return f"fsar/room-{int(room_id)}/stage/{kind}-{ref}"


def git(
    cwd: str | Path, *args: str, env: dict[str, str] | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *GIT_SAFE, "-C", str(cwd), *args],
        capture_output=True, text=True, input=input,
        env={**os.environ, **env} if env else None,
    )


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS room_member_stages (
                room_id      INTEGER NOT NULL,
                kind         TEXT NOT NULL,
                ref          TEXT NOT NULL,
                stage_path   TEXT NOT NULL,
                baseline_ref TEXT NOT NULL,
                workspace_id INTEGER NOT NULL,
                created_at   TEXT NOT NULL,
                PRIMARY KEY (room_id, kind, ref)
            )
            """
        )
        conn.commit()


def _lookup(db_path: str, room_id: int, kind: str, ref: str) -> sqlite3.Row | None:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM room_member_stages "
            "WHERE room_id = ? AND kind = ? AND ref = ?",
            (int(room_id), kind, str(ref)),
        ).fetchone()


def _forget(db_path: str, room_id: int, kind: str, ref: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM room_member_stages "
            "WHERE room_id = ? AND kind = ? AND ref = ?",
            (int(room_id), kind, str(ref)),
        )
        conn.commit()


def stage_of(
    workspaces: WorkspaceRepo, room_id: int, kind: str, ref: str,
) -> sqlite3.Row | None:
    _ensure_table(str(workspaces.db_path))
    return _lookup(str(workspaces.db_path), room_id, kind, ref)


def baseline_for(project_root: str | Path) -> str:
    result = git(project_root, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise StageError(f"cannot read HEAD of {project_root}: {result.stderr.strip()}")
    return result.stdout.strip()


def ensure_stage(
    workspaces: WorkspaceRepo, project_root: str | Path,
    room_id: int, kind: str, ref: str,
) -> Workspace:
    db = str(workspaces.db_path)
    _ensure_table(db)
    existing = _lookup(db, room_id, kind, ref)
    if existing is not None:
        if Path(existing["stage_path"]).exists():
            found = workspaces.get(int(existing["workspace_id"]))
            if found is not None:
                return found
        _forget(db, room_id, kind, ref)

    project_root = Path(project_root)
    if not (project_root / ".git").exists():
        raise StageError(f"{project_root} is not a git repository")

    path = stage_path(room_id, kind, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = baseline_for(project_root)
    branch = branch_for(room_id, kind, ref)
    added = git(project_root, "worktree", "add", "-b", branch, str(path), baseline)
    if added.returncode != 0:
        raise StageError(f"worktree add failed: {added.stderr.strip()}")

    workspace = workspaces.create(
        name=f"room-{int(room_id)}-{kind}-{ref}", root_path=str(path),
    )
    with _connect(db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO room_member_stages "
            "(room_id, kind, ref, stage_path, baseline_ref, workspace_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(room_id), kind, str(ref), str(path), baseline, int(workspace.id),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return workspace


def remove_stage(
    workspaces: WorkspaceRepo, project_root: str | Path,
    room_id: int, kind: str, ref: str,
) -> bool:
    db = str(workspaces.db_path)
    _ensure_table(db)
    row = _lookup(db, room_id, kind, ref)
    if row is None:
        return False
    git(project_root, "worktree", "remove", "--force", str(row["stage_path"]))
    workspaces.delete(int(row["workspace_id"]))
    _forget(db, room_id, kind, ref)
    return True
