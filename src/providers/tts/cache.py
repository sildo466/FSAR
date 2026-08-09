# SPDX-License-Identifier: MIT
"""Two-tier cache for synthesized speech audio."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path

L1_MAX_ENTRIES = 256
L1_TTL_SEC = 3600
L2_MAX_BYTES = 500 * 1024 * 1024
L2_TTL_SEC = 7 * 24 * 3600
L2_DB_PATH = Path("data/tts_cache.db")

_l1: OrderedDict[str, tuple[bytes, str, float]] = OrderedDict()
_l1_lock = threading.Lock()
_l2_lock = threading.Lock()


def tts_cache_key(
    provider_id: str,
    voice: str,
    model: str,
    text: str,
    instructions: str = "",
) -> str:
    digest = hashlib.sha256(
        f"{provider_id}|{voice}|{model}|{text}|{instructions}".encode("utf-8")
    ).hexdigest()
    return f"tts:{provider_id}:{voice}:{model}:{digest[:16]}"


def l1_clear() -> None:
    with _l1_lock:
        _l1.clear()


def l1_get(key: str) -> bytes | None:
    with _l1_lock:
        entry = _l1.get(key)
        if entry is None:
            return None
        audio, _mime, expires_at = entry
        if expires_at < time.time():
            _l1.pop(key, None)
            return None
        _l1.move_to_end(key)
        return audio


def l1_put(key: str, audio: bytes, mime: str = "audio/mpeg") -> None:
    with _l1_lock:
        _l1[key] = (audio, mime, time.time() + L1_TTL_SEC)
        _l1.move_to_end(key)
        while len(_l1) > L1_MAX_ENTRIES:
            _l1.popitem(last=False)


def _initialize_unlocked() -> None:
    L2_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(L2_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tts_cache (
                cache_key TEXT PRIMARY KEY,
                audio BLOB NOT NULL,
                mime TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                voice TEXT NOT NULL,
                model TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                text_len INTEGER NOT NULL,
                created_at REAL NOT NULL,
                last_used_at REAL NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tts_last_used "
            "ON tts_cache(last_used_at)"
        )


def l2_get(key: str) -> tuple[bytes, str] | None:
    with _l2_lock:
        _initialize_unlocked()
        now = time.time()
        with sqlite3.connect(L2_DB_PATH) as connection:
            row = connection.execute(
                "SELECT audio, mime, created_at FROM tts_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            audio, mime, created_at = row
            if now - float(created_at) > L2_TTL_SEC:
                connection.execute(
                    "DELETE FROM tts_cache WHERE cache_key = ?", (key,)
                )
                return None
            connection.execute(
                "UPDATE tts_cache SET last_used_at = ?, hit_count = hit_count + 1 "
                "WHERE cache_key = ?",
                (now, key),
            )
            return bytes(audio), str(mime)


def l2_put(
    key: str,
    audio: bytes,
    mime: str,
    provider_id: str,
    voice: str,
    model: str,
    text_len: int,
) -> None:
    with _l2_lock:
        _initialize_unlocked()
        now = time.time()
        with sqlite3.connect(L2_DB_PATH) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO tts_cache
                    (cache_key, audio, mime, provider_id, voice, model,
                     text_hash, text_len, created_at, last_used_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    key,
                    sqlite3.Binary(audio),
                    mime,
                    provider_id,
                    voice,
                    model,
                    key.rsplit(":", 1)[-1],
                    text_len,
                    now,
                    now,
                ),
            )
            total = int(
                connection.execute(
                    "SELECT COALESCE(SUM(length(audio)), 0) FROM tts_cache"
                ).fetchone()[0]
            )
            if total <= L2_MAX_BYTES:
                return
            rows = connection.execute(
                "SELECT cache_key, length(audio) FROM tts_cache "
                "ORDER BY last_used_at ASC, rowid ASC"
            ).fetchall()
            for stale_key, size in rows:
                if total <= L2_MAX_BYTES:
                    break
                connection.execute(
                    "DELETE FROM tts_cache WHERE cache_key = ?", (stale_key,)
                )
                total -= int(size or 0)


def l2_clear() -> None:
    with _l2_lock:
        if L2_DB_PATH.exists():
            L2_DB_PATH.unlink()
        _initialize_unlocked()


def l2_total_bytes() -> int:
    with _l2_lock:
        if not L2_DB_PATH.exists():
            return 0
        _initialize_unlocked()
        with sqlite3.connect(L2_DB_PATH) as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(length(audio)), 0) FROM tts_cache"
            ).fetchone()
        return int(row[0] if row else 0)
