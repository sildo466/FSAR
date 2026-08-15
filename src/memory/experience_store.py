"""FSAR Experience Layer — Phase 6.

DB-first procedural knowledge + memory chunks. Replaces a filesystem
SKILL.md / sidecar pattern with SQLite rows.

Tables (all in the same `data/memory.db` as the rest of the memory system):
    experiences                — main procedural knowledge (replaces SKILL.md)
    experience_templates       — (replaces templates/<name>)
    experience_scripts         — (replaces scripts/<name>)
    experience_references      — (replaces references/<name>)
    experience_links           — (replaces related_skills frontmatter)
    memory_chunks              — (replaces MEMORY.md / USER.md prose)

Lifecycle: pure SQL state machine — active → stale → archived. Pinned rows
bypass all auto-transitions.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.utils.config import get_config
from src.utils.logger import logger


STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"

VALID_STATES = {STATE_ACTIVE, STATE_STALE, STATE_ARCHIVED}


@dataclass
class Experience:
    id: int | None = None
    name: str = ""
    category: str = ""
    description: str = ""
    body: str = ""
    trigger_patterns: list[str] = field(default_factory=list)
    pitfalls: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    use_count: int = 0
    last_used_at: str | None = None
    state: str = STATE_ACTIVE
    pinned: bool = False
    created_by: str = "agent"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "body": self.body,
            "trigger_patterns": list(self.trigger_patterns),
            "pitfalls": list(self.pitfalls),
            "prerequisites": list(self.prerequisites),
            "use_count": self.use_count,
            "last_used_at": self.last_used_at,
            "state": self.state,
            "pinned": bool(self.pinned),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ExperienceTemplate:
    id: int | None = None
    experience_id: int = 0
    name: str = ""
    content: str = ""


@dataclass
class ExperienceScript:
    id: int | None = None
    experience_id: int = 0
    name: str = ""
    language: str = "python"
    content: str = ""


@dataclass
class ExperienceReference:
    id: int | None = None
    experience_id: int = 0
    title: str = ""
    body: str = ""
    source: str = ""
    source_url: str = ""
    created_at: str = ""


@dataclass
class ExperienceLink:
    src_id: int = 0
    dst_id: int = 0
    relation: str = "related"
    weight: float = 1.0


@dataclass
class MemoryChunk:
    id: int | None = None
    source: str = "memory"
    title: str = ""
    body: str = ""
    chunk_index: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "body": self.body,
            "chunk_index": self.chunk_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ProposedExperience:
    name: str
    category: str
    description: str
    body: str
    suggested_strategy: str
    occurrence_count: int


class ExperienceStore:
    """SQLite-backed store for procedural knowledge + memory chunks."""

    def __init__(self, db_path: str | Path | None = None, config=None):
        config = config or get_config()
        self._config = config
        self._db_path = Path(db_path or config.memory_sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    body TEXT NOT NULL,
                    trigger_patterns TEXT NOT NULL DEFAULT '[]',
                    pitfalls TEXT NOT NULL DEFAULT '[]',
                    prerequisites TEXT NOT NULL DEFAULT '[]',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT,
                    state TEXT NOT NULL DEFAULT 'active',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experiences_category
                    ON experiences(category);
                CREATE INDEX IF NOT EXISTS idx_experiences_state
                    ON experiences(state);
                CREATE INDEX IF NOT EXISTS idx_experiences_last_used
                    ON experiences(last_used_at);

                CREATE TABLE IF NOT EXISTS experience_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experience_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experience_scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experience_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    language TEXT NOT NULL,
                    content TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experience_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experience_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source TEXT,
                    source_url TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experience_links (
                    src_id INTEGER NOT NULL,
                    dst_id INTEGER NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    PRIMARY KEY (src_id, dst_id, relation)
                );

                CREATE TABLE IF NOT EXISTS memory_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_source
                    ON memory_chunks(source);
            """)
            conn.commit()

    # ---------- Experience CRUD ----------

    def upsert_experience(self, exp: Experience) -> int:
        """Create or update an experience row. Returns row id."""
        if not exp.name or not exp.category or not exp.body:
            raise ValueError("experience requires name, category, body")
        from src.skills.memory_sanitize import Sanitizer
        Sanitizer(self._config).enforce(exp.body)
        if exp.state not in VALID_STATES:
            raise ValueError(f"invalid state: {exp.state!r}")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO experiences (
                    name, category, description, body,
                    trigger_patterns, pitfalls, prerequisites,
                    state, pinned, created_by,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    category=excluded.category,
                    description=excluded.description,
                    body=excluded.body,
                    trigger_patterns=excluded.trigger_patterns,
                    pitfalls=excluded.pitfalls,
                    prerequisites=excluded.prerequisites,
                    state=excluded.state,
                    pinned=excluded.pinned,
                    updated_at=excluded.updated_at
            """, (
                exp.name, exp.category, exp.description, exp.body,
                json.dumps(exp.trigger_patterns, ensure_ascii=False),
                json.dumps(exp.pitfalls, ensure_ascii=False),
                json.dumps(exp.prerequisites, ensure_ascii=False),
                exp.state, 1 if exp.pinned else 0,
                exp.created_by or "agent",
                exp.created_at or now, now,
            ))
            conn.commit()
            row = conn.execute(
                "SELECT id FROM experiences WHERE name = ?", (exp.name,)
            ).fetchone()
            return int(row[0])

    def get_by_name(self, name: str) -> Experience | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiences WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            return None
        return _row_to_experience(row)

    def get_by_id(self, exp_id: int) -> Experience | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiences WHERE id = ?", (exp_id,)
            ).fetchone()
        if not row:
            return None
        return _row_to_experience(row)

    def list_for_index(self, *, categories: Iterable[str] | None = None,
                       include_states: Iterable[str] = (STATE_ACTIVE,)) -> list[Experience]:
        """Return experiences visible to LLM index (active by default)."""
        states = list(include_states)
        wheres = ["state IN ({})".format(",".join("?" * len(states)))]
        params: list[Any] = list(states)
        if categories is not None:
            cats = list(categories)
            wheres.append("category IN ({})".format(",".join("?" * len(cats))))
            params.extend(cats)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM experiences WHERE {' AND '.join(wheres)} "
                "ORDER BY category, name",
                params,
            ).fetchall()
        return [_row_to_experience(r) for r in rows]

    def delete_experience(self, name: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM experiences WHERE name = ?", (name,))
            conn.commit()
            return cur.rowcount > 0

    # ---------- Child rows ----------

    def _replace_templates(self, exp_id: int, templates: list[ExperienceTemplate]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM experience_templates WHERE experience_id = ?", (exp_id,))
            for t in templates:
                conn.execute("""
                    INSERT INTO experience_templates (experience_id, name, content)
                    VALUES (?, ?, ?)
                """, (exp_id, t.name, t.content))
            conn.commit()

    def _replace_scripts(self, exp_id: int, scripts: list[ExperienceScript]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM experience_scripts WHERE experience_id = ?", (exp_id,))
            for s in scripts:
                conn.execute("""
                    INSERT INTO experience_scripts (experience_id, name, language, content)
                    VALUES (?, ?, ?, ?)
                """, (exp_id, s.name, s.language, s.content))
            conn.commit()

    def _replace_references(self, exp_id: int, refs: list[ExperienceReference]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM experience_references WHERE experience_id = ?", (exp_id,))
            now = datetime.now().isoformat(timespec="seconds")
            for r in refs:
                conn.execute("""
                    INSERT INTO experience_references
                        (experience_id, title, body, source, source_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    exp_id, r.title, r.body,
                    r.source or "paste", r.source_url,
                    r.created_at or now,
                ))
            conn.commit()

    def save_experience_full(self, exp: Experience, *,
                             templates: list[ExperienceTemplate] | None = None,
                             scripts: list[ExperienceScript] | None = None,
                             references: list[ExperienceReference] | None = None) -> int:
        """Upsert experience + replace child rows in one shot."""
        exp_id = self.upsert_experience(exp)
        if templates is not None:
            self._replace_templates(exp_id, templates)
        if scripts is not None:
            self._replace_scripts(exp_id, scripts)
        if references is not None:
            self._replace_references(exp_id, references)
        return exp_id

    def get_templates(self, exp_id: int) -> list[ExperienceTemplate]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, experience_id, name, content
                FROM experience_templates WHERE experience_id = ?
                ORDER BY id
            """, (exp_id,)).fetchall()
        return [
            ExperienceTemplate(id=r[0], experience_id=r[1], name=r[2], content=r[3])
            for r in rows
        ]

    def get_scripts(self, exp_id: int) -> list[ExperienceScript]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, experience_id, name, language, content
                FROM experience_scripts WHERE experience_id = ?
                ORDER BY id
            """, (exp_id,)).fetchall()
        return [
            ExperienceScript(id=r[0], experience_id=r[1],
                             name=r[2], language=r[3], content=r[4])
            for r in rows
        ]

    def get_references(self, exp_id: int) -> list[ExperienceReference]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, experience_id, title, body, source, source_url, created_at
                FROM experience_references WHERE experience_id = ?
                ORDER BY id
            """, (exp_id,)).fetchall()
        return [
            ExperienceReference(
                id=r[0], experience_id=r[1], title=r[2], body=r[3],
                source=r[4] or "", source_url=r[5] or "", created_at=r[6] or "",
            )
            for r in rows
        ]

    def render_experience_body(self, exp: Experience) -> str:
        """Format full experience body for LLM (returned by experience_view tool)."""
        parts = [
            f"# {exp.name}",
            f"_Category: {exp.category} | state: {exp.state} | uses: {exp.use_count}_",
            f"\n## Procedure\n{exp.body}",
        ]
        if exp.pitfalls:
            parts.append("\n## Pitfalls")
            for p in exp.pitfalls:
                parts.append(f"- {p}")
        if exp.prerequisites:
            parts.append("\n## Prerequisites")
            for p in exp.prerequisites:
                parts.append(f"- {p}")
        templates = self.get_templates(exp.id) if exp.id else []
        for tpl in templates:
            parts.append(f"\n## Template: {tpl.name}\n```\n{tpl.content}\n```")
        scripts = self.get_scripts(exp.id) if exp.id else []
        for scr in scripts:
            parts.append(f"\n## Script: {scr.name} ({scr.language})\n```{scr.language}\n{scr.content}\n```")
        refs = self.get_references(exp.id) if exp.id else []
        for ref in refs:
            src = f" ({ref.source_url})" if ref.source_url else ""
            parts.append(f"\n## Reference: {ref.title}{src}\n{ref.body}")
        return "\n".join(parts)

    # ---------- Usage tracking ----------

    def bump_use(self, name: str) -> int:
        """Increment use_count + update last_used_at. Returns new use_count.

        Active rows stay active; stale rows auto-promote back to active on use.
        """
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute("""
                UPDATE experiences
                SET use_count = use_count + 1,
                    last_used_at = ?,
                    state = CASE WHEN state = 'stale' THEN 'active' ELSE state END
                WHERE name = ?
            """, (now, name))
            conn.commit()
            row = conn.execute(
                "SELECT use_count, state FROM experiences WHERE name = ?", (name,)
            ).fetchone()
        return int(row[0]) if row else 0

    # ---------- Lifecycle ----------

    def mark_stale(self, *, days: int = 30) -> int:
        """active → stale. Skip pinned rows + rows used within window.

        Returns affected row count.
        """
        with self._connect() as conn:
            cur = conn.execute(f"""
                UPDATE experiences
                SET state = 'stale', updated_at = ?
                WHERE pinned = 0
                  AND state = 'active'
                  AND (
                    (last_used_at IS NOT NULL
                     AND last_used_at < datetime('now', ?))
                    OR (use_count = 0
                        AND created_at < datetime('now', ?))
                  )
            """, (
                datetime.now().isoformat(timespec="seconds"),
                f"-{days} days",
                f"-{days} days",
            ))
            conn.commit()
            return cur.rowcount

    def mark_archived(self, *, days: int = 90) -> int:
        """stale → archived. Skip pinned rows."""
        with self._connect() as conn:
            cur = conn.execute(f"""
                UPDATE experiences
                SET state = 'archived', updated_at = ?
                WHERE pinned = 0
                  AND state = 'stale'
                  AND (last_used_at IS NULL
                       OR last_used_at < datetime('now', ?))
            """, (
                datetime.now().isoformat(timespec="seconds"),
                f"-{days} days",
            ))
            conn.commit()
            return cur.rowcount

    def set_state(self, name: str, state: str) -> bool:
        if state not in VALID_STATES:
            raise ValueError(f"invalid state: {state!r}")
        with self._connect() as conn:
            cur = conn.execute("""
                UPDATE experiences SET state = ?, updated_at = ?
                WHERE name = ?
            """, (state, datetime.now().isoformat(timespec="seconds"), name))
            conn.commit()
            return cur.rowcount > 0

    def set_pinned(self, name: str, pinned: bool) -> bool:
        with self._connect() as conn:
            cur = conn.execute("""
                UPDATE experiences SET pinned = ?, updated_at = ?
                WHERE name = ?
            """, (1 if pinned else 0,
                  datetime.now().isoformat(timespec="seconds"),
                  name))
            conn.commit()
            return cur.rowcount > 0

    # ---------- Indexing for LLM system prompt ----------

    def render_index(self, *, max_desc_chars: int = 60,
                     compact_categories: Iterable[str] | None = None) -> str:
        """Render the ## Experiences index block for system prompt injection.

        Experiences grouped by category. Description truncated to max_desc_chars.
        """
        compact = set(compact_categories or [])
        exps = self.list_for_index()
        if not exps:
            return ""
        by_cat: dict[str, list[Experience]] = {}
        for e in exps:
            by_cat.setdefault(e.category, []).append(e)
        lines = ["## Experiences (task matches one below → MUST call experience_view(name) first → FOLLOW its SKILL.md exactly)"]
        for cat in sorted(by_cat):
            show_in_compact = cat in compact
            if not show_in_compact:
                lines.append(f"  {cat}:")
            for e in by_cat[cat]:
                desc = (e.description or "").strip().replace("\n", " ")
                if len(desc) > max_desc_chars:
                    desc = desc[:max_desc_chars - 1] + "…"
                prefix = "    -" if show_in_compact else "    -"
                lines.append(f"{prefix} {e.name}: {desc}")
        lines.append("")
        lines.append(
            "[Skill loading rule] If the task matches one of the skills above, your FIRST "
            "step MUST be to call experience_view(name=\"...\") to load it, then execute the "
            "task. Do NOT skip this step; do NOT read skill-directory files via "
            "file_ops/run_command instead of experience_view. After loading, follow the "
            "SKILL.md exactly (copy the seed template, obey Non-Negotiables). Load only "
            "the single matching skill."
        )
        return "\n".join(lines)

    # ---------- P5 → P6 auto-promote bridge ----------

    def propose_from_reflections(self, *, threshold: int = 3) -> list[ProposedExperience]:
        """Cluster task_reflections.suggested_strategy; surface clusters ≥threshold.

        Pure SQL GROUP BY — no LLM call. Returns ProposedExperience rows the
        user (or auto-promote at intensity=high) can confirm.

        Returns [] when task_reflections table doesn't exist (test isolation,
        cold DB). Caller should call after at least one reflection.
        """
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1 FROM task_reflections LIMIT 0").fetchall()
        except sqlite3.OperationalError:
            return []
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT suggested_strategy, COUNT(*) AS n,
                       MIN(outcome) AS sample_outcome
                FROM task_reflections
                WHERE suggested_strategy != ''
                GROUP BY suggested_strategy
                HAVING n >= ?
                ORDER BY n DESC
            """, (threshold,)).fetchall()
        out: list[ProposedExperience] = []
        for r in rows:
            strategy = r[0].strip()
            if not strategy:
                continue
            slug = _slugify(strategy)
            out.append(ProposedExperience(
                name=f"task_strategy::{slug}"[:60],
                category="task-strategies",
                description=strategy[:60],
                body=f"Auto-promoted from {r[1]} task_reflections.\n\n{strategy}",
                suggested_strategy=strategy,
                occurrence_count=int(r[1]),
            ))
        return out

    def auto_promote(self, *, threshold: int = 3) -> int:
        """Promote every cluster ≥threshold as an active experience row.

        Returns count of newly created rows. Existing rows (same name) are
        skipped — use propose_from_reflections + manual upsert to refresh.
        """
        now = datetime.now().isoformat(timespec="seconds")
        promoted = 0
        for prop in self.propose_from_reflections(threshold=threshold):
            existing = self.get_by_name(prop.name)
            if existing is not None:
                continue
            self.upsert_experience(Experience(
                name=prop.name,
                category=prop.category,
                description=prop.description,
                body=prop.body,
                created_by="task_reflection",
                created_at=now,
                updated_at=now,
            ))
            promoted += 1
        if promoted:
            logger.info(f"auto_promote: created {promoted} experience row(s)")
        return promoted

    # ---------- Memory chunks ----------

    def add_chunk(self, *, source: str, title: str, body: str,
                  chunk_index: int = 0) -> int:
        """Insert a memory chunk. Returns row id."""
        if not source or not title:
            raise ValueError("chunk requires source + title")
        from src.skills.memory_sanitize import Sanitizer
        Sanitizer(self._config).enforce(body)
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO memory_chunks (source, title, body, chunk_index, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source, title, body, chunk_index, now, now))
            conn.commit()
            return int(cur.lastrowid)

    def list_chunks(self, *, source: str | None = None,
                    limit: int = 100) -> list[MemoryChunk]:
        with self._connect() as conn:
            if source is not None:
                rows = conn.execute("""
                    SELECT id, source, title, body, chunk_index, created_at, updated_at
                    FROM memory_chunks WHERE source = ?
                    ORDER BY chunk_index, id LIMIT ?
                """, (source, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, source, title, body, chunk_index, created_at, updated_at
                    FROM memory_chunks ORDER BY chunk_index, id LIMIT ?
                """, (limit,)).fetchall()
        return [
            MemoryChunk(
                id=r[0], source=r[1], title=r[2], body=r[3],
                chunk_index=r[4], created_at=r[5], updated_at=r[6],
            )
            for r in rows
        ]

    def search_chunks(self, keyword: str, *, limit: int = 10) -> list[MemoryChunk]:
        """Keyword search on memory_chunks.

        Builds LIKE patterns from the query — full text plus 2-char CJK
        sliding-window bigrams — so rephrased queries still hit.
        """
        if not keyword:
            return []
        patterns = self._expand_patterns(keyword)
        if not patterns:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        for pat in patterns:
            like = f"%{pat}%"
            clauses.append("(title LIKE ? OR body LIKE ?)")
            params.extend([like, like])
        where = " OR ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT id, source, title, body, chunk_index, created_at, updated_at
                FROM memory_chunks
                WHERE {where}
                GROUP BY id
                ORDER BY updated_at DESC LIMIT ?
            """, (*params, limit)).fetchall()
        return [
            MemoryChunk(
                id=r[0], source=r[1], title=r[2], body=r[3],
                chunk_index=r[4], created_at=r[5], updated_at=r[6],
            )
            for r in rows
        ]

    @staticmethod
    def _expand_patterns(query: str) -> list[str]:
        """Build LIKE patterns from a query.

        Always include the full query; for CJK runs >1 char, also add 2-char
        sliding windows. Dedupe, longest-first.
        """
        import re
        out: list[str] = []
        q = query.strip()
        if not q:
            return out
        out.append(q)
        for run in re.findall(r"[一-鿿]+", q):
            if len(run) == 1:
                out.append(run)
            else:
                for i in range(len(run) - 1):
                    out.append(run[i:i + 2])
        seen: set[str] = set()
        deduped: list[str] = []
        for p in out:
            if p and p not in seen:
                seen.add(p)
                deduped.append(p)
        deduped.sort(key=len, reverse=True)
        return deduped

    def render_memory_chunks_block(self, *, limit: int = 5) -> str:
        """Render a flat ## Memory block (caller filters by relevance later)."""
        chunks = self.list_chunks(limit=limit)
        if not chunks:
            return ""
        lines = [f"## Memory ({len(chunks)} chunks)"]
        for c in chunks:
            body = c.body.strip().replace("\n", " ")
            if len(body) > 200:
                body = body[:199] + "…"
            lines.append(f"- [{c.source}] {c.title}: {body}")
        return "\n".join(lines)

    def delete_chunk(self, chunk_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_chunks WHERE id = ?", (chunk_id,))
            conn.commit()
            return cur.rowcount > 0


# ---------- helpers ----------

def _row_to_experience(row: sqlite3.Row | tuple) -> Experience:
    """Convert a SELECT * row to Experience dataclass."""
    cols = (
        "id", "name", "category", "description", "body",
        "trigger_patterns", "pitfalls", "prerequisites",
        "use_count", "last_used_at", "state", "pinned",
        "created_by", "created_at", "updated_at",
    )
    if isinstance(row, sqlite3.Row):
        kv = {c: row[c] for c in row.keys()}
    else:
        kv = dict(zip(cols, row))
    return Experience(
        id=kv["id"],
        name=kv["name"] or "",
        category=kv["category"] or "",
        description=kv["description"] or "",
        body=kv["body"] or "",
        trigger_patterns=json.loads(kv["trigger_patterns"] or "[]"),
        pitfalls=json.loads(kv["pitfalls"] or "[]"),
        prerequisites=json.loads(kv["prerequisites"] or "[]"),
        use_count=int(kv["use_count"] or 0),
        last_used_at=kv["last_used_at"],
        state=kv["state"] or STATE_ACTIVE,
        pinned=bool(kv["pinned"]),
        created_by=kv["created_by"] or "agent",
        created_at=kv["created_at"] or "",
        updated_at=kv["updated_at"] or "",
    )


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", text.lower()).strip("_")
    return s[:50] or "experience"
