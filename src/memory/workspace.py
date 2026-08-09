"""SQLite persistence for sandbox workspaces, bindings, and audit events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Workspace:
    id: int
    name: str
    root_path: str
    allowed_paths: list[str]
    blocked_patterns: list[str]
    default_for_new: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkspaceRepo:
    def __init__(self, db_path: str | Path, *, config_dir: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.config_dir = Path(config_dir) if config_dir else self.db_path.parent
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self.ensure_tables(conn)
        self.seed_default_if_empty()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                root_path TEXT NOT NULL,
                allowed_paths TEXT NOT NULL DEFAULT '["**"]',
                blocked_patterns TEXT NOT NULL DEFAULT '[]',
                default_for_new INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_default
                ON workspaces(default_for_new) WHERE default_for_new = 1;
            CREATE TABLE IF NOT EXISTS conversation_workspaces (
                conversation_id TEXT PRIMARY KEY,
                workspace_id INTEGER NOT NULL,
                granted_at TEXT NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_conv_ws_workspace
                ON conversation_workspaces(workspace_id);
            CREATE TABLE IF NOT EXISTS sandbox_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                conversation_id TEXT,
                workspace_id INTEGER,
                tool TEXT NOT NULL,
                operation TEXT,
                target_path TEXT,
                command TEXT,
                verdict TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_session ON sandbox_audit(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_created ON sandbox_audit(created_at DESC);
            """
        )
        conn.commit()

    def seed_default_if_empty(self) -> Workspace | None:
        if self.list():
            return None
        root = Path.home() / "FSAR-workspace"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            root = self.config_dir / "FSAR-workspace"
            root.mkdir(parents=True, exist_ok=True)
        return self.create(name="Sandbox", root_path=str(root.resolve()), set_default=True)

    def list(self) -> list[Workspace]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM workspaces ORDER BY default_for_new DESC, name COLLATE NOCASE").fetchall()
        return [self._row(row) for row in rows]

    def get(self, workspace_id: int) -> Workspace | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        return self._row(row) if row else None

    def get_default_for_new(self) -> Workspace | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE default_for_new = 1").fetchone()
        return self._row(row) if row else None

    def create(self, *, name: str, root_path: str, allowed_paths: list[str] | None = None,
               blocked_patterns: list[str] | None = None, set_default: bool = False) -> Workspace:
        if not name.strip():
            raise ValueError("workspace name is required")
        if not root_path.strip():
            raise ValueError("workspace root path is required")
        now = datetime.now().isoformat()
        resolved = str(Path(root_path).expanduser().resolve(strict=False))
        with self._connect() as conn:
            if set_default:
                conn.execute("UPDATE workspaces SET default_for_new = 0, updated_at = ?", (now,))
            cur = conn.execute(
                "INSERT INTO workspaces (name, root_path, allowed_paths, blocked_patterns, default_for_new, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name.strip(), resolved, json.dumps(allowed_paths if allowed_paths is not None else ["**"]), json.dumps(blocked_patterns or []), int(set_default), now, now),
            )
            workspace_id = int(cur.lastrowid)
            conn.commit()
        workspace = self.get(workspace_id)
        assert workspace is not None
        return workspace

    def update(self, workspace_id: int, **fields: Any) -> Workspace:
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in {"name", "root_path", "allowed_paths", "blocked_patterns"}:
                continue
            if key in {"allowed_paths", "blocked_patterns"}:
                value = json.dumps(value)
            elif key == "root_path":
                value = str(Path(value).expanduser().resolve(strict=False))
            updates.append(f"{key} = ?")
            values.append(value)
        if not updates:
            workspace = self.get(workspace_id)
            if workspace is None:
                raise KeyError(workspace_id)
            return workspace
        updates.append("updated_at = ?")
        values.extend([datetime.now().isoformat(), workspace_id])
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
        if cur.rowcount == 0:
            raise KeyError(workspace_id)
        workspace = self.get(workspace_id)
        assert workspace is not None
        return workspace

    def delete(self, workspace_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT default_for_new FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if not row:
                return False
            if bool(row[0]):
                raise ValueError("the default workspace cannot be deleted")
            cur = conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            conn.commit()
        return cur.rowcount > 0

    def set_default_for_new(self, workspace_id: int) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone() is None:
                raise KeyError(workspace_id)
            conn.execute("UPDATE workspaces SET default_for_new = 0, updated_at = ? WHERE default_for_new = 1", (now,))
            conn.execute("UPDATE workspaces SET default_for_new = 1, updated_at = ? WHERE id = ?", (now, workspace_id))
            conn.commit()

    def get_binding(self, conversation_id: str) -> tuple[str, int] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT conversation_id, workspace_id FROM conversation_workspaces WHERE conversation_id = ?", (conversation_id,)).fetchone()
        return (str(row[0]), int(row[1])) if row else None

    def bind(self, conversation_id: str, workspace_id: int) -> None:
        if self.get(workspace_id) is None:
            raise KeyError(workspace_id)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversation_workspaces (conversation_id, workspace_id, granted_at) VALUES (?, ?, ?) ON CONFLICT(conversation_id) DO UPDATE SET workspace_id = excluded.workspace_id, granted_at = excluded.granted_at",
                (conversation_id, workspace_id, datetime.now().isoformat()),
            )
            conn.commit()

    def get_or_create_binding(self, conversation_id: str) -> Workspace:
        binding = self.get_binding(conversation_id)
        if binding:
            workspace = self.get(binding[1])
            if workspace:
                return workspace
        workspace = self.get_default_for_new()
        if workspace is None:
            raise RuntimeError("sandbox has no default workspace")
        self.bind(conversation_id, workspace.id)
        self.append_audit(
            session_id=conversation_id, conversation_id=conversation_id, workspace_id=workspace.id,
            tool="workspace", operation="bind", target_path=workspace.root_path,
            command=None, verdict="binding_created", reason="conversation bound to default workspace",
        )
        return workspace

    def append_audit(self, *, session_id: str | None, conversation_id: str | None,
                     workspace_id: int | None, tool: str, operation: str | None,
                     target_path: str | None, command: str | None, verdict: str,
                     reason: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sandbox_audit (session_id, conversation_id, workspace_id, tool, operation, target_path, command, verdict, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, conversation_id, workspace_id, tool, operation, target_path, command, verdict, reason, datetime.now().isoformat()),
            )
            conn.commit()
        return int(cur.lastrowid)

    def list_audit(self, *, since: str | None = None, conversation_id: str | None = None,
                   limit: int = 50) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if since:
            clauses.append("created_at >= ?")
            values.append(since)
        if conversation_id:
            clauses.append("conversation_id = ?")
            values.append(conversation_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM sandbox_audit{where} ORDER BY created_at DESC LIMIT ?", values).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> Workspace:
        return Workspace(
            id=int(row["id"]), name=str(row["name"]), root_path=str(row["root_path"]),
            allowed_paths=list(json.loads(row["allowed_paths"])),
            blocked_patterns=list(json.loads(row["blocked_patterns"])),
            default_for_new=bool(row["default_for_new"]),
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
        )
