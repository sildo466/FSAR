"""Tests for Gemini cachedContents cache + factory dispatch."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.gemini_cache import (
    GeminiCacheEntry,
    GeminiPromptCache,
    compute_match_key,
    digest_system_prompt,
    resolve_ttl,
    resolve_refresh_window_s,
)


# --- Match key ----------------------------------------------------------------

def test_match_key_independent_of_dict_order():
    base = dict(provider="google", model_id="gemini-1.5-pro", model_api=None,
                base_url="https://generativelanguage.googleapis.com/v1beta",
                system_prompt="you are helpful")
    a = compute_match_key(**base)
    b = compute_match_key(**dict(base, system_prompt="you are helpful"))
    assert a == b


def test_match_key_differs_on_model_id():
    base = dict(provider="google", model_api=None,
                base_url="https://generativelanguage.googleapis.com/v1beta",
                system_prompt="x")
    assert compute_match_key(model_id="gemini-1.5-pro", **base) != \
           compute_match_key(model_id="gemini-2.0-flash", **base)


def test_match_key_differs_on_system_prompt():
    base = dict(provider="google", model_id="gemini-1.5-pro", model_api=None,
                base_url="https://generativelanguage.googleapis.com/v1beta")
    assert compute_match_key(system_prompt="alpha", **base) != \
           compute_match_key(system_prompt="beta", **base)


def test_ttl_resolution():
    assert resolve_ttl("short") == "300s"
    assert resolve_ttl("long") == "3600s"


def test_refresh_window_resolution():
    assert resolve_refresh_window_s("short") == 30
    assert resolve_refresh_window_s("long") == 5 * 60


# --- Lifecycle (mocked google.genai) ------------------------------------------

class _FakeCacheObj:
    def __init__(self, name, expire_time):
        self.name = name
        self.expire_time = expire_time


def _make_cache_client(*, on_create=None, on_update=None):
    client = MagicMock()
    client.caches.create.side_effect = on_create or (lambda **kw: _FakeCacheObj(
        name="cachedContents/abc", expire_time=datetime.now(timezone.utc) + timedelta(hours=1)))
    client.caches.update.side_effect = on_update or (lambda **kw: _FakeCacheObj(
        name="cachedContents/abc", expire_time=datetime.now(timezone.utc) + timedelta(hours=1)))
    return client


def test_ensure_creates_on_first_call():
    with tempfile.TemporaryDirectory() as d:
        client_factory = lambda **kw: _make_cache_client()
        c = GeminiPromptCache(db_path=str(Path(d) / "g.db"), client_factory=client_factory)
        result = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="you are helpful",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        assert result == "cachedContents/abc"
        s = c.stats()
        assert s["ready"] >= 1


def test_ensure_returns_existing_when_not_expired():
    with tempfile.TemporaryDirectory() as d:
        client = _make_cache_client()
        c = GeminiPromptCache(db_path=str(Path(d) / "g.db"), client_factory=lambda **kw: client)
        c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="you are helpful",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        prev_create_count = client.caches.create.call_count
        # Second call: should NOT create again because ready entry exists.
        result = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="you are helpful",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        assert result == "cachedContents/abc"
        assert client.caches.create.call_count == prev_create_count  # no extra POST


def test_ensure_refreshes_when_close_to_expiry():
    with tempfile.TemporaryDirectory() as d:
        client = _make_cache_client()
        c = GeminiPromptCache(db_path=str(Path(d) / "g.db"), client_factory=lambda **kw: client)
        first = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="you are helpful",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        assert first == "cachedContents/abc"
        # Inject a near-expiry state (expire in 5 seconds, well within the
        # 30s short-refresh window).
        import sqlite3 as _sq
        with _sq.connect(str(Path(d) / "g.db")) as conn:
            conn.execute(
                "UPDATE gemini_prompt_cache SET expire_time = ?",
                ((datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),),
            )
            conn.commit()
        prev_update = client.caches.update.call_count
        result = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="you are helpful",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        assert result == "cachedContents/abc"
        assert client.caches.update.call_count == prev_update + 1


def test_ensure_fails_open_when_create_raises():
    with tempfile.TemporaryDirectory() as d:
        def client_factory(**kw):
            client = MagicMock()
            client.caches.create.side_effect = RuntimeError("transient")
            return client
        c = GeminiPromptCache(db_path=str(Path(d) / "g.db"), client_factory=client_factory)
        result = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="x",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        assert result is None
        # Subsequent calls within backoff window should also return None.
        result2 = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="x",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            cache_retention="short",
            api_key="test-key",
        )
        assert result2 is None


def test_ensure_skips_when_no_system_prompt():
    with tempfile.TemporaryDirectory() as d:
        c = GeminiPromptCache(
            db_path=str(Path(d) / "g.db"),
            client_factory=lambda **kw: _make_cache_client(),
        )
        result = c.ensure_cached_content(
            model_id="gemini-1.5-pro",
            system_prompt="",
            base_url="x",
            cache_retention="short",
            api_key="key",
        )
        assert result is None


def test_normalize_model_id_prepends_models():
    with tempfile.TemporaryDirectory() as d:
        c = GeminiPromptCache(db_path=str(Path(d) / "g.db"))
        assert c._normalize_model_id("gemini-1.5-pro") == "models/gemini-1.5-pro"
        assert c._normalize_model_id("models/gemini-1.5-pro") == "models/gemini-1.5-pro"
        assert c._normalize_model_id("tunedModels/x") == "tunedModels/x"
