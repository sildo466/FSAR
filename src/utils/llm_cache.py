"""Two-tier LLM response cache.

L1: in-process LRU + TTL (cheap, hot path).
L2: SQLite (survives restarts).

Key derivation:
    sha256(stable_json({"model", "messages", "tools", "temperature", "top_p",
                        "max_tokens", "stream"}))

Messages are JSON-serialized with sort_keys and stable Unicode handling so the
same logical payload always hashes to the same digest regardless of dict key
ordering.

Design notes:
- Only non-streaming, deterministic calls are cached. Streaming responses
  cannot be losslessly roundtripped through serialization without buffering
  every chunk, so we skip caching when stream=True.
- Vision calls (image_url base64) and tool calls in flight are best-effort:
  callers may opt-in via `cache_enabled=True` or opt-out via `cache_enabled=False`.
- L2 writes are wrapped in a try/except so a corrupt disk never breaks the
  request — on read errors we silently miss and fall through to the network.

Ported from openclaw's `ExpiringMapCache` + per-session cache state pattern
(`src/agents/cache-utils.ts`, `src/agents/pi-embedded-runner/cache-ttl.ts`),
adapted to fsar's Python + SQLite stack.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional


def stable_dumps(obj: Any) -> str:
    """Deterministic JSON: sort_keys, ensure_ascii off, separators tight."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def make_cache_key(payload: dict) -> str:
    """Hash a request payload dict into a stable SHA-256 hex digest."""
    encoded = stable_dumps(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _ExpiringLRU:
    """Thread-safe in-memory TTL cache with LRU eviction.

    Mirrors openclaw's `createExpiringMapCache` semantics: lazy prune on read,
    configurable max size, per-entry `stored_at` epoch seconds.
    """

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 300.0):
        self._max = max(1, int(max_entries))
        self._ttl = max(0.0, float(ttl_seconds))
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        if self._ttl == 0:
            return None
        now = time.time()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if now - stored_at > self._ttl:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        if self._ttl == 0:
            return
        now = time.time()
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (now, value)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._data), "max": self._max, "ttl_seconds": self._ttl}


class LLMCache:
    """Two-tier (L1 in-memory + L2 SQLite) LLM response cache."""

    def __init__(
        self,
        db_path: str | Path = "data/llm_cache.db",
        l1_max_entries: int = 256,
        l1_ttl_seconds: float = 300.0,
        l2_ttl_seconds: float = 86400.0,
        enabled: bool = True,
    ):
        self.enabled = bool(enabled)
        self.l2_ttl = max(0.0, float(l2_ttl_seconds))
        self._l1 = _ExpiringLRU(max_entries=l1_max_entries, ttl_seconds=l1_ttl_seconds) if self.enabled else None
        self._db_path = str(db_path)
        self._db_lock = threading.Lock()
        self._stats = {"l1_hit": 0, "l2_hit": 0, "miss": 0, "writes": 0, "skipped": 0}
        if self.enabled:
            self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._db_lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    last_hit_at REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_cache_expires ON llm_cache(expires_at)")
            conn.commit()

    @staticmethod
    def _should_skip(stream: bool, cache_enabled: Optional[bool]) -> bool:
        """Streaming cannot be losslessly cached; explicit False opts out."""
        if cache_enabled is False:
            return True
        if stream:
            return True
        return False

    def get(
        self,
        payload: dict,
        cache_enabled: Optional[bool] = None,
    ) -> Optional[Any]:
        """Look up a cached response. Returns None on miss / disabled / skip."""
        if not self.enabled:
            return None
        stream = bool(payload.get("stream"))
        if self._should_skip(stream, cache_enabled):
            return None
        key = make_cache_key(payload)
        if self._l1 is not None:
            v = self._l1.get(key)
            if v is not None:
                self._stats["l1_hit"] += 1
                return v
        row = self._read_l2(key)
        if row is None:
            self._stats["miss"] += 1
            return None
        self._stats["l2_hit"] += 1
        if self._l1 is not None:
            self._l1.set(key, row)
        self._bump_l2_hit(key)
        return row

    def put(
        self,
        payload: dict,
        response: Any,
        cache_enabled: Optional[bool] = None,
    ) -> None:
        """Store a response in both L1 and L2 (if eligible)."""
        if not self.enabled:
            return
        stream = bool(payload.get("stream"))
        if self._should_skip(stream, cache_enabled):
            self._stats["skipped"] += 1
            return
        key = make_cache_key(payload)
        if self._l1 is not None:
            self._l1.set(key, response)
        self._write_l2(key, payload, response)
        self._stats["writes"] += 1

    def _read_l2(self, key: str) -> Optional[Any]:
        try:
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    "SELECT response_json, expires_at FROM llm_cache WHERE key = ?",
                    (key,),
                )
                row = cur.fetchone()
            if row is None:
                return None
            response_json, expires_at = row
            if self.l2_ttl > 0 and expires_at and expires_at < time.time():
                try:
                    with self._db_lock, sqlite3.connect(self._db_path) as conn:
                        conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
                        conn.commit()
                except Exception:
                    pass
                return None
            return json.loads(response_json)
        except Exception:
            return None

    def _write_l2(self, key: str, payload: dict, response: Any) -> None:
        try:
            now = time.time()
            expires = now + self.l2_ttl if self.l2_ttl > 0 else now + 86400 * 365
            model = str(payload.get("model", ""))
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO llm_cache
                        (key, model, request_json, response_json,
                         created_at, expires_at, hit_count, last_hit_at)
                    VALUES (?, ?, ?, ?, ?, ?,
                            COALESCE((SELECT hit_count FROM llm_cache WHERE key = ?), 0),
                            (SELECT last_hit_at FROM llm_cache WHERE key = ?))
                    """,
                    (
                        key,
                        model,
                        stable_dumps(payload),
                        stable_dumps(_to_jsonable(response)),
                        now,
                        expires,
                        key,
                        key,
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def _bump_l2_hit(self, key: str) -> None:
        try:
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "UPDATE llm_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE key = ?",
                    (time.time(), key),
                )
                conn.commit()
        except Exception:
            pass

    def stats(self) -> dict:
        out = dict(self._stats)
        if self._l1 is not None:
            out["l1"] = self._l1.stats()
        return out

    def get_stats(self) -> dict:
        """Aggregated stats for the Usage page. See docs/superpowers/plans
        §8.4 — keys are fixed for the wire schema."""
        l1 = self._l1.stats() if self._l1 is not None else {"size": 0, "max": 0}
        l2 = self._l2_stats()
        l1_lookup = self._stats["l1_hit"] + self._stats["miss"]
        l2_lookup = self._stats["l2_hit"] + self._stats["miss"]
        return {
            "l1_entries": int(l1.get("size", 0)),
            "l1_capacity": int(l1.get("max", 0)),
            "l1_hit_rate": round(self._stats["l1_hit"] / l1_lookup, 4) if l1_lookup else 0.0,
            "l2_entries": int(l2.get("entries", 0)),
            "l2_size_bytes": int(l2.get("size_bytes", 0)),
            "l2_hit_rate": round(self._stats["l2_hit"] / l2_lookup, 4) if l2_lookup else 0.0,
        }

    def _l2_stats(self) -> dict:
        try:
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(LENGTH(response_json)), 0) "
                    "FROM llm_cache"
                ).fetchone()
            return {"entries": int(row[0] or 0), "size_bytes": int(row[1] or 0)}
        except Exception:
            return {"entries": 0, "size_bytes": 0}

    def clear(self) -> None:
        if self._l1 is not None:
            self._l1.clear()
        try:
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM llm_cache")
                conn.commit()
        except Exception:
            pass


def _to_jsonable(obj: Any) -> Any:
    """Coerce SDK response objects (with attributes / pydantic models) into
    plain JSON-serializable structures."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    # Pydantic v2 models: model_dump(); v1: dict()
    for method in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                return _to_jsonable(fn())
            except Exception:
                pass
    # Fallback: read __dict__ of the object (works for OpenAI response objects
    # which are simple namespaces).
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        return _to_jsonable(d)
    return str(obj)


_DEFAULT_CACHE: Optional[LLMCache] = None
_DEFAULT_LOCK = threading.Lock()


def get_default_cache() -> LLMCache:
    """Process-wide singleton. Lazily constructed on first call."""
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_CACHE is None:
                from src.utils.config import get_config

                cfg = get_config()
                _DEFAULT_CACHE = LLMCache(
                    db_path=cfg.llm_cache_db_path,
                    l1_max_entries=cfg.llm_cache_l1_max_entries,
                    l1_ttl_seconds=cfg.llm_cache_l1_ttl_seconds,
                    l2_ttl_seconds=cfg.llm_cache_l2_ttl_seconds,
                    enabled=cfg.llm_cache_enabled,
                )
    return _DEFAULT_CACHE
