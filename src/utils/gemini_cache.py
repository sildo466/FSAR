"""Gemini cachedContents cache — provider-side prompt cache for Gemini.

Implements the provider-side prompt-cache flow:
- POST `/cachedContents` on miss — captures `system_prompt` as a server-side
  reusable prefix; server returns a `cachedContent` resource name to attach
  to subsequent generate_content calls.
- PATCH `cachedContents/<id>?updateMask=ttl` to extend TTL before expiry.
- Persistent state per (provider, model_id, model_api, base_url,
  sha256(system_prompt)) so callers reuse the same cachedContent across
  requests without re-creating.

State is persisted in the same SQLite file as `LLMCache` (`data/llm_cache.db`)
under table `gemini_prompt_cache`. One row per match key (latest state wins),
plus failure rows with `retry_after`.

API shape via `google.genai` SDK:
    client = genai.Client(api_key=...)
    cached = client.caches.create(
        model="models/<model_id>",
        config=types.CreateCachedContentConfig(
            ttl="300s" | "3600s",
            system_instruction=<text>,
        ),
    )
    # cached.name  = "cachedContents/xxxxx"
    # cached.expire_time = datetime

    client.caches.update(
        name="cachedContents/xxxxx",
        config=types.UpdateCachedContentConfig(ttl="3600s"),
    )

    client.models.generate_content(
        model="models/<model_id>",
        contents=<contents>,
        config=types.GenerateContentConfig(
            cached_content="cachedContents/xxxxx",
        ),
    )
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def digest_system_prompt(system_prompt: str) -> str:
    return hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()


def compute_match_key(
    *,
    provider: str,
    model_id: str,
    model_api: Optional[str],
    base_url: str,
    system_prompt: str,
) -> str:
    """Stable JSON match key."""
    payload = {
        "provider": provider,
        "modelId": model_id,
        "modelApi": model_api,
        "baseUrl": base_url,
        "systemPromptDigest": digest_system_prompt(system_prompt),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def resolve_ttl(cache_retention: str) -> str:
    return "3600s" if cache_retention == "long" else "300s"


def resolve_refresh_window_s(cache_retention: str) -> int:
    return 5 * 60 if cache_retention == "long" else 30


def _parse_expire_iso(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return None


@dataclass
class GeminiCacheEntry:
    status: str  # "ready" | "failed"
    timestamp: float
    provider: str
    model_id: str
    model_api: Optional[str]
    base_url: str
    system_prompt_digest: str
    cache_retention: str
    cached_content: Optional[str] = None
    expire_time: Optional[str] = None
    retry_after: Optional[float] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.status != "ready":
            return False
        ts = _parse_expire_iso(self.expire_time)
        if ts is None:
            return False
        return ts <= (now if now is not None else time.time())

    def needs_refresh(self, cache_retention: str, now: Optional[float] = None) -> bool:
        if self.status != "ready":
            return False
        ts = _parse_expire_iso(self.expire_time)
        if ts is None:
            return False
        return ts - (now if now is not None else time.time()) <= resolve_refresh_window_s(cache_retention)


class GeminiPromptCache:
    """Persistent Gemini cachedContents cache."""

    RETRY_BACKOFF_S = 10 * 60

    def __init__(
        self,
        db_path: str | Path = "data/llm_cache.db",
        client_factory=None,
    ):
        """`client_factory` returns a google.genai Client when invoked; defaults
        to constructing one from `GEMINI_API_KEY`/the active provider config."""
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._client_factory = client_factory
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gemini_prompt_cache (
                    match_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_api TEXT,
                    base_url TEXT NOT NULL,
                    system_prompt_digest TEXT NOT NULL,
                    cache_retention TEXT NOT NULL,
                    cached_content TEXT,
                    expire_time TEXT,
                    retry_after REAL,
                    error_message TEXT,
                    status_code INTEGER
                )
                """
            )
            conn.commit()

    def _read(self, match_key: str) -> Optional[GeminiCacheEntry]:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    """SELECT status, timestamp, provider, model_id, model_api, base_url,
                              system_prompt_digest, cache_retention, cached_content,
                              expire_time, retry_after, error_message, status_code
                       FROM gemini_prompt_cache WHERE match_key = ?""",
                    (match_key,),
                )
                row = cur.fetchone()
            if row is None:
                return None
            return GeminiCacheEntry(
                status=row[0],
                timestamp=row[1],
                provider=row[2],
                model_id=row[3],
                model_api=row[4],
                base_url=row[5],
                system_prompt_digest=row[6],
                cache_retention=row[7],
                cached_content=row[8],
                expire_time=row[9],
                retry_after=row[10],
                error_message=row[11],
                status_code=row[12],
            )
        except Exception:
            return None

    def _write(self, match_key: str, entry: GeminiCacheEntry) -> None:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO gemini_prompt_cache
                       (match_key, status, timestamp, provider, model_id, model_api,
                        base_url, system_prompt_digest, cache_retention,
                        cached_content, expire_time, retry_after,
                        error_message, status_code)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        match_key,
                        entry.status,
                        entry.timestamp,
                        entry.provider,
                        entry.model_id,
                        entry.model_api,
                        entry.base_url,
                        entry.system_prompt_digest,
                        entry.cache_retention,
                        entry.cached_content,
                        entry.expire_time,
                        entry.retry_after,
                        entry.error_message,
                        entry.status_code,
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def _build_client(self, api_key: str, base_url: Optional[str] = None):
        """Construct a google.genai Client. Optional override via client_factory."""
        if self._client_factory is not None:
            return self._client_factory(api_key=api_key, base_url=base_url)
        try:
            from google import genai  # type: ignore

            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                try:
                    from google.genai import types as _t  # type: ignore

                    kwargs["http_options"] = _t.HttpOptions(base_url=base_url)
                except Exception:
                    pass
            return genai.Client(**kwargs)
        except Exception:
            return None

    def _normalize_model_id(self, model_id: str) -> str:
        m = (model_id or "").strip()
        if not m:
            return m
        if m.startswith("models/") or m.startswith("tunedModels/"):
            return m
        return f"models/{m}"

    def _create(self, client, *, model_id: str, system_prompt: str, ttl: str) -> Optional[dict]:
        """Return {"cached_content": str, "expire_time": str|None} on success,
        {"error": str} on SDK failure, or None when the SDK returned no name."""
        try:
            from google.genai import types  # type: ignore

            cached = client.caches.create(
                model=model_id,
                config=types.CreateCachedContentConfig(
                    ttl=ttl,
                    system_instruction=system_prompt,
                ),
            )
            name = getattr(cached, "name", None)
            if not name:
                return None
            expire = getattr(cached, "expire_time", None)
            expire_iso = expire.isoformat() if hasattr(expire, "isoformat") else str(expire) if expire else None
            return {"cached_content": name, "expire_time": expire_iso}
        except Exception as e:
            return {"error": str(e)[:500]}

    def _refresh(self, client, *, cached_content: str, ttl: str) -> Optional[str]:
        try:
            from google.genai import types  # type: ignore

            updated = client.caches.update(
                name=cached_content,
                config=types.UpdateCachedContentConfig(ttl=ttl),
            )
            expire = getattr(updated, "expire_time", None)
            return expire.isoformat() if hasattr(expire, "isoformat") else str(expire) if expire else None
        except Exception:
            return None

    def ensure_cached_content(
        self,
        *,
        model_id: str,
        system_prompt: str,
        base_url: str,
        cache_retention: str,
        api_key: str,
        provider: str = "google",
        model_api: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Optional[str]:
        """Return the cachedContent resource name to attach to subsequent
        generate_content calls. Returns None when the API is unavailable,
        a recent failure is in backoff, or creation genuinely failed.

        All signature/state-digest/db side effects follow the
        `ensureGooglePromptCache` semantics.
        """
        if not api_key or not system_prompt:
            return None
        normalized_model = self._normalize_model_id(model_id)
        match_key = compute_match_key(
            provider=provider,
            model_id=normalized_model,
            model_api=model_api,
            base_url=base_url,
            system_prompt=system_prompt,
        )
        now = now if now is not None else time.time()

        existing = self._read(match_key)

        if existing and existing.status == "failed" and existing.retry_after and existing.retry_after > now:
            return None

        client = self._build_client(api_key, base_url)
        if client is None:
            return None

        ttl = resolve_ttl(cache_retention)

        if existing and existing.status == "ready" and existing.cached_content:
            if not existing.is_expired(now):
                if not existing.needs_refresh(cache_retention, now):
                    return existing.cached_content
                new_expire = self._refresh(
                    client,
                    cached_content=existing.cached_content,
                    ttl=ttl,
                )
                if new_expire:
                    self._write(
                        match_key,
                        GeminiCacheEntry(
                            status="ready",
                            timestamp=now,
                            provider=provider,
                            model_id=normalized_model,
                            model_api=model_api,
                            base_url=base_url,
                            system_prompt_digest=digest_system_prompt(system_prompt),
                            cache_retention=cache_retention,
                            cached_content=existing.cached_content,
                            expire_time=new_expire,
                        )
                    )
                return existing.cached_content

        created = self._create(client, model_id=normalized_model, system_prompt=system_prompt, ttl=ttl)
        if created is None:
            return None
        if "error" in created:
            self._write(
                match_key,
                GeminiCacheEntry(
                    status="failed",
                    timestamp=now,
                    provider=provider,
                    model_id=normalized_model,
                    model_api=model_api,
                    base_url=base_url,
                    system_prompt_digest=digest_system_prompt(system_prompt),
                    cache_retention=cache_retention,
                    retry_after=now + self.RETRY_BACKOFF_S,
                    error_message=created["error"],
                )
            )
            return None
        self._write(
            match_key,
            GeminiCacheEntry(
                status="ready",
                timestamp=now,
                provider=provider,
                model_id=normalized_model,
                model_api=model_api,
                base_url=base_url,
                system_prompt_digest=digest_system_prompt(system_prompt),
                cache_retention=cache_retention,
                cached_content=created["cached_content"],
                expire_time=created["expire_time"],
            )
        )
        return created["cached_content"]


def get_default_gemini_cache() -> GeminiPromptCache:

    def stats(self) -> dict:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    "SELECT status, COUNT(*) FROM gemini_prompt_cache GROUP BY status"
                )
                counts = dict(cur.fetchall())
            return {"ready": counts.get("ready", 0), "failed": counts.get("failed", 0)}
        except Exception:
            return {"ready": 0, "failed": 0}


_DEFAULT: Optional[GeminiPromptCache] = None
_DEFAULT_LOCK = threading.Lock()


def get_default_gemini_cache() -> GeminiPromptCache:
    global _DEFAULT
    if _DEFAULT is None:
        with _DEFAULT_LOCK:
            if _DEFAULT is None:
                from src.utils.config import get_config
                _DEFAULT = GeminiPromptCache(db_path=get_config().llm_cache_db_path)
    return _DEFAULT
