# SPDX-License-Identifier: MIT
"""TTS L1/L2 cache tests."""

import sqlite3

import pytest

from src.providers.tts import cache


@pytest.fixture
def isolated_cache(monkeypatch, tmp_path):
    db_path = tmp_path / "tts-cache.db"
    monkeypatch.setattr(cache, "L2_DB_PATH", db_path)
    cache.l1_clear()
    cache.l2_clear()
    yield db_path
    cache.l1_clear()


def test_cache_key_is_deterministic_and_voice_sensitive():
    first = cache.tts_cache_key("p1", "alloy", "tts-1", "hello")
    second = cache.tts_cache_key("p1", "alloy", "tts-1", "hello")
    changed = cache.tts_cache_key("p1", "echo", "tts-1", "hello")
    assert first == second
    assert first != changed
    assert first.startswith("tts:p1:alloy:tts-1:")
    assert len(first.rsplit(":", 1)[-1]) == 16


def test_l1_put_get_and_capacity(isolated_cache):
    for index in range(cache.L1_MAX_ENTRIES + 5):
        cache.l1_put(f"k{index}", b"audio")
    assert cache.l1_get("k0") is None
    assert cache.l1_get(f"k{cache.L1_MAX_ENTRIES + 4}") == b"audio"


def test_l1_expiry(isolated_cache, monkeypatch):
    now = 1000.0
    monkeypatch.setattr(cache.time, "time", lambda: now)
    cache.l1_put("key", b"audio")
    now += cache.L1_TTL_SEC + 1
    assert cache.l1_get("key") is None


def test_l2_put_get_and_total(isolated_cache):
    cache.l2_put("k1", b"a" * 1000, "audio/mpeg", "p1", "v", "m", 4)
    cache.l2_put("k2", b"b" * 2000, "audio/mpeg", "p1", "v", "m", 4)
    assert cache.l2_get("k1") == (b"a" * 1000, "audio/mpeg")
    assert cache.l2_total_bytes() == 3000


def test_l2_expiry_removes_entry(isolated_cache, monkeypatch):
    cache.l2_put("key", b"audio", "audio/mpeg", "p1", "v", "m", 4)
    with sqlite3.connect(isolated_cache) as connection:
        connection.execute(
            "UPDATE tts_cache SET created_at = created_at - ? WHERE cache_key = ?",
            (cache.L2_TTL_SEC + 1, "key"),
        )
    assert cache.l2_get("key") is None


def test_l2_lru_eviction_when_over_cap(isolated_cache, monkeypatch):
    monkeypatch.setattr(cache, "L2_MAX_BYTES", 5000)
    for index in range(10):
        cache.l2_put(
            f"k{index}", b"x" * 1000, "audio/mpeg", "p1", "v", "m", 1
        )
    assert cache.l2_total_bytes() <= 5000
    assert cache.l2_get("k9") is not None
    assert cache.l2_get("k0") is None


def test_cache_key_includes_instructions_dimension():
    from src.providers.tts.cache import tts_cache_key

    plain = tts_cache_key("p1", "Cherry", "qwen3-tts-flash", "hello")
    styled = tts_cache_key(
        "p1", "Cherry", "qwen3-tts-flash", "hello", "speak cheerfully"
    )
    assert plain != styled


def test_cache_key_default_instructions_backward_compatible():
    from src.providers.tts.cache import tts_cache_key

    assert tts_cache_key("p1", "v", "m", "t") == tts_cache_key("p1", "v", "m", "t", "")
