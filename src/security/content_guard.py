# SPDX-License-Identifier: MIT
"""Quarantine and whitelist bookkeeping for content screening.

The store is the single owner of the two new tables. Nothing else writes them.
Callers in src/memory reach this module through get_guard(), imported inside
the function body so the memory layer never hard-depends on the security layer.
"""

from __future__ import annotations

import hashlib
import json
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from src.security.content_screen import DEFAULT_THRESHOLD, ContentScreener, ScreenVerdict
from src.utils.config import get_config
from src.utils.logger import logger

QUARANTINE_TABLE = "content_quarantine"
WHITELIST_TABLE = "content_whitelist"

SCAN_STORES = [
    "semantic_doc",
    "chunk",
    "experience",
    "preference",
    "pattern",
    "reflection",
    "card",
]

_CARD_TEXT_FIELDS = (
    "description",
    "personality",
    "scenario",
    "system_prompt_override",
    "example_dialogues",
)

_GUARD: "ContentGuard | None" = None


def _build_guard() -> "ContentGuard":
    return ContentGuard(get_config())


def get_guard() -> "ContentGuard":
    global _GUARD
    if _GUARD is None:
        _GUARD = _build_guard()
    return _GUARD


def reset_guard() -> None:
    global _GUARD
    _GUARD = None


@dataclass
class QuarantineItem:
    store: str
    record_ref: str
    text: str
    kind: str
    original_fields: dict | None = None


class StoreAdapter(Protocol):
    name: str

    def enumerate(self) -> list[QuarantineItem]: ...

    def remove(self, item: QuarantineItem) -> bool: ...

    def restore(self, item: QuarantineItem, text: str) -> bool: ...


class ContentGuard:
    def __init__(self, config, *, screener=None, db_path=None, autostart: bool = True) -> None:
        self.config = config
        self.screener = screener if screener is not None else ContentScreener(config)
        path = db_path or config.get("memory.sqlite_path")
        if path is None:
            path = getattr(config, "memory_sqlite_path", None)
        if path is None:
            path = Path("data") / "memory.db"
        self.db_path = Path(path)
        self._report: dict = {}
        self._queue: "queue.Queue | None" = None
        self._thread: threading.Thread | None = None
        self._init_db()
        if autostart:
            self._start_worker()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store TEXT NOT NULL,
                    record_ref TEXT NOT NULL,
                    text TEXT NOT NULL,
                    original_fields TEXT,
                    sha256 TEXT NOT NULL,
                    verdict_confidence REAL NOT NULL,
                    screened_by TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'quarantined',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {WHITELIST_TABLE} (
                    sha256 TEXT PRIMARY KEY,
                    added_by TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ---------- worker ----------

    def _start_worker(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._worker_loop, name="content-guard", daemon=True
        )
        self._thread.start()

    def _worker_loop(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                adapter, store, record_ref, text, kind = job
                self._judge_items(
                    [QuarantineItem(store, record_ref, text, kind)], kind=kind, adapter=adapter
                )
            except Exception as exc:
                logger.warning(f"content guard worker error: {exc}")
            finally:
                self._queue.task_done()

    def pending(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    def flush(self, timeout: float = 10.0) -> bool:
        if self._queue is None:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("security.content_screening.enabled", True))

    @property
    def threshold(self) -> float:
        raw = self.config.get("security.content_screening.threshold", DEFAULT_THRESHOLD)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return DEFAULT_THRESHOLD

    @staticmethod
    def digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _screened_by(self) -> str:
        return "jev" if getattr(self.screener, "_jev", None) is not None else "llm"

    # ---------- whitelist ----------

    def is_whitelisted(self, text: str) -> bool:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT 1 FROM {WHITELIST_TABLE} WHERE sha256 = ?",
                    (self.digest(text),),
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning(f"whitelist lookup failed, treating as not whitelisted: {exc}")
            return False

    def add_to_whitelist(self, text: str, *, added_by: str, note: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WHITELIST_TABLE} (sha256, added_by, note, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sha256) DO NOTHING
                """,
                (
                    self.digest(text),
                    added_by,
                    note,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

    def remove_from_whitelist(self, text: str) -> bool:
        return self.remove_hash_from_whitelist(self.digest(text))

    def remove_hash_from_whitelist(self, sha256: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM {WHITELIST_TABLE} WHERE sha256 = ?", (sha256,)
            )
            conn.commit()
            return cur.rowcount > 0

    def list_whitelist(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT sha256, added_by, note, created_at FROM {WHITELIST_TABLE} "
                "ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- quarantine ----------

    def record(
        self,
        store: str,
        record_ref: str,
        text: str,
        *,
        kind: str,
        verdict: ScreenVerdict,
        original_fields: dict | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO {QUARANTINE_TABLE} (
                    store, record_ref, text, original_fields, sha256,
                    verdict_confidence, screened_by, state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'quarantined', ?)
                """,
                (
                    store,
                    str(record_ref),
                    text,
                    json.dumps(original_fields, ensure_ascii=False) if original_fields else None,
                    self.digest(text),
                    float(verdict.confidence),
                    self._screened_by(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        out = dict(row)
        raw = out.get("original_fields")
        out["original_fields"] = json.loads(raw) if raw else None
        return out

    def get_quarantine(self, qid: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {QUARANTINE_TABLE} WHERE id = ?", (qid,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_quarantine(self, *, include_resolved: bool = False) -> list[dict]:
        sql = f"SELECT * FROM {QUARANTINE_TABLE}"
        if not include_resolved:
            sql += " WHERE state = 'quarantined'"
        sql += " ORDER BY id DESC"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _set_state(self, qid: int, state: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE {QUARANTINE_TABLE} SET state = ? WHERE id = ? AND state = 'quarantined'",
                (state, qid),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_restored(self, qid: int) -> bool:
        return self._set_state(qid, "restored")

    def purge(self, qid: int) -> bool:
        return self._set_state(qid, "purged")

    # ---------- reporting ----------

    def set_report(self, report: dict) -> None:
        self._report = dict(report)

    def get_report(self) -> dict:
        return dict(self._report)

    # ---------- serving ----------

    def _adapter_for(self, name: str, adapters=None):
        for adapter in adapters if adapters is not None else default_adapters(self.config):
            if adapter.name == name:
                return adapter
        return None

    def submit(self, *, store: str, record_ref: str, text: str, kind: str) -> None:
        if not self.enabled or not text.strip():
            return
        self._enqueue(store, str(record_ref), text, kind)

    def submit_for_test(self, adapter, *, store, record_ref, text, kind) -> None:
        if not self.enabled or not text.strip():
            return
        self._enqueue(store, str(record_ref), text, kind, adapter=adapter)

    def _enqueue(self, store, record_ref, text, kind, *, adapter=None) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._start_worker()
        if adapter is None:
            adapter = self._adapter_for(store)
            if adapter is None:
                return
        self._queue.put((adapter, store, record_ref, text, kind))

    def flush_or_raise(self, timeout: float = 10.0) -> None:
        assert self.flush(timeout), f"guard queue did not drain: {self.pending()} pending"

    # ---------- judging ----------

    def _judge_items(self, items: list[QuarantineItem], *, kind: str, adapter=None) -> dict:
        report = {"scanned": 0, "quarantined": 0, "unavailable": 0}
        pending: dict[str, QuarantineItem] = {}
        for idx, item in enumerate(items):
            if self.is_whitelisted(item.text):
                continue
            pending[f"k{idx}"] = item

        if not pending:
            return report

        verdicts = self.screener.screen_batch(
            {k: i.text for k, i in pending.items()}, kind=kind
        )
        for key, item in pending.items():
            report["scanned"] += 1
            verdict = verdicts.get(key)
            if verdict is None or verdict.unavailable:
                report["unavailable"] += 1
                continue
            if not verdict.flagged:
                continue
            try:
                self.record(
                    item.store,
                    item.record_ref,
                    item.text,
                    kind=item.kind,
                    verdict=verdict,
                    original_fields=item.original_fields,
                )
            except Exception as exc:
                logger.warning(
                    f"quarantine write failed for {item.store}:{item.record_ref}: {exc}"
                )
                continue
            try:
                target = adapter if adapter is not None else self._adapter_for(item.store)
                ok = bool(target and target.remove(item))
            except Exception as exc:
                logger.warning(f"removal failed for {item.store}:{item.record_ref}: {exc}")
                ok = False
            if not ok:
                continue
            report["quarantined"] += 1
        return report

    def scan_all(self, adapters=None) -> dict:
        if not self.enabled:
            self.set_report({"enabled": False})
            return {"scanned": 0, "quarantined": 0, "unavailable": 0, "total": 0}

        if adapters is None:
            adapters = default_adapters(self.config)

        totals = {"scanned": 0, "quarantined": 0, "unavailable": 0}
        total_items = 0
        for adapter in adapters:
            try:
                items = adapter.enumerate()
            except Exception as exc:
                logger.warning(f"content scan could not enumerate {adapter.name}: {exc}")
                continue
            total_items += len(items)
            kind = items[0].kind if items else adapter.name
            report = self._judge_items(items, kind=kind, adapter=adapter)
            for key in totals:
                totals[key] += report[key]

        summary = {**totals, "total": total_items}
        self.set_report(summary)
        logger.info(f"content scan finished: {summary}")
        return summary

    def restore(self, qid: int, adapters=None) -> bool:
        row = self.get_quarantine(qid)
        if row is None or row["state"] != "quarantined":
            return False
        adapter = self._adapter_for(row["store"], adapters)
        if adapter is None:
            return False
        item = QuarantineItem(
            store=row["store"],
            record_ref=row["record_ref"],
            text=row["text"],
            kind="",
            original_fields=row["original_fields"],
        )
        try:
            if not adapter.restore(item, row["text"]):
                return False
        except Exception as exc:
            logger.warning(f"restore failed for {row['store']}:{row['record_ref']}: {exc}")
            return False
        self.add_to_whitelist(row["text"], added_by="restore")
        self.mark_restored(qid)
        return True


# ---------- store adapters ----------


class _SemanticAdapter:
    name = "semantic_doc"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        out = []
        for doc_id, text, meta in self.store.list_all():
            if str(meta.get("role", "")) != "user":
                continue
            out.append(QuarantineItem(self.name, doc_id, text, self.name))
        return out

    def remove(self, item):
        return self.store.delete([item.record_ref]) > 0

    def restore(self, item, text):
        return bool(self.store.add(text, doc_id=item.record_ref, role="user"))


class _ChunkAdapter:
    name = "chunk"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        return [
            QuarantineItem(self.name, str(c.id), c.body, "memory_chunk", {"title": c.title})
            for c in self.store.list_all_chunks()
        ]

    def remove(self, item):
        return self.store.delete_chunk(int(item.record_ref))

    def restore(self, item, text):
        self.store.add_chunk(
            source="user_fact",
            title=(item.original_fields or {}).get("title") or "restored",
            body=text,
        )
        return True


class _ExperienceAdapter:
    name = "experience"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        from src.memory.experience_store import VALID_STATES

        return [
            QuarantineItem(
                self.name, e.name, e.body, "memory_chunk", {"category": e.category}
            )
            for e in self.store.list_for_index(
                categories=None, include_states=VALID_STATES
            )
        ]

    def remove(self, item):
        return self.store.delete_experience(item.record_ref)

    def restore(self, item, text):
        existing = self.store.get_by_name(item.record_ref)
        if existing is None:
            return False
        existing.body = text
        self.store.upsert_experience(existing)
        return True


class _PreferenceAdapter:
    name = "preference"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        return [
            QuarantineItem(self.name, key, f"{key}: {pref.value}", "preference")
            for key, pref in self.store.get_all_preferences().items()
        ]

    def remove(self, item):
        return self.store.delete_preference(item.record_ref)

    def restore(self, item, text):
        if ": " not in text:
            return False
        key, value = text.split(": ", 1)
        self.store.set_preference(key, value, source="restored")
        return True


class _PatternAdapter:
    name = "pattern"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        return [
            QuarantineItem(self.name, p["pattern"], p["pattern"], "pattern")
            for p in self.store.get_top_patterns(limit=1000000)
        ]

    def remove(self, item):
        return self.store.delete_pattern(item.record_ref)

    def restore(self, item, text):
        self.store.record_pattern(text, evidence="restored")
        return True


class _ReflectionAdapter:
    name = "reflection"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        return [
            QuarantineItem(self.name, str(r["id"]), r["suggested_strategy"], "reflection")
            for r in self.store.list_recent(limit=1000000)
            if r.get("suggested_strategy")
        ]

    def remove(self, item):
        return self.store.delete_reflection(int(item.record_ref))

    def restore(self, item, text):
        return False


class _CardAdapter:
    name = "card"

    def __init__(self, store):
        self.store = store

    def enumerate(self):
        out = []
        for card in self.store.list_characters():
            fields = {f: getattr(card, f, "") or "" for f in _CARD_TEXT_FIELDS}
            text = "\n".join(str(v) for v in fields.values() if v)
            if not text.strip():
                continue
            out.append(
                QuarantineItem(self.name, str(card.id), text, "character_card", fields)
            )
        return out

    def remove(self, item):
        card = self.store.get_character(int(item.record_ref))
        if card is None:
            return False
        for field in _CARD_TEXT_FIELDS:
            setattr(card, field, "[]" if field == "example_dialogues" else "")
        self.store.upsert_character(card)
        return True

    def restore(self, item, text):
        card = self.store.get_character(int(item.record_ref))
        if card is None:
            return False
        for field, value in (item.original_fields or {}).items():
            setattr(card, field, value)
        self.store.upsert_character(card)
        return True


def default_adapters(config) -> list:
    from pathlib import Path

    from src.memory.cards import CardRepo
    from src.memory.experience_store import ExperienceStore
    from src.memory.reflection import ReflectionStore
    from src.memory.semantic import SemanticMemory
    from src.memory.user_model import UserModel

    db = config.memory_sqlite_path
    return [
        _SemanticAdapter(SemanticMemory()),
        _ChunkAdapter(ExperienceStore(db)),
        _ExperienceAdapter(ExperienceStore(db)),
        _PreferenceAdapter(UserModel(db)),
        _PatternAdapter(UserModel(db)),
        _ReflectionAdapter(ReflectionStore(db)),
        _CardAdapter(CardRepo(Path(db))),
    ]

