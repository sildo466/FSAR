"""Tests for L1+L2 LLM cache and provider cache marker hooks."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.llm_cache import (
    LLMCache,
    _ExpiringLRU,
    make_cache_key,
    stable_dumps,
)
from src.utils.llm_factory import (
    apply_provider_cache_markers,
    cached_chat_completion,
    detect_provider_family,
    reset_clients,
)


# --- Cache key determinism -----------------------------------------------------

def test_stable_dumps_ignores_dict_order():
    a = stable_dumps({"b": 1, "a": 2, "c": 3})
    b = stable_dumps({"c": 3, "a": 2, "b": 1})
    assert a == b


def test_make_cache_key_independent_of_key_order():
    p1 = {"model": "x", "messages": [{"role": "user", "content": "hi"}], "temperature": 0}
    p2 = {"temperature": 0, "messages": [{"content": "hi", "role": "user"}], "model": "x"}
    assert make_cache_key(p1) == make_cache_key(p2)


def test_make_cache_key_changes_with_payload():
    p1 = {"model": "x", "messages": [{"role": "user", "content": "hi"}]}
    p2 = {"model": "x", "messages": [{"role": "user", "content": "bye"}]}
    assert make_cache_key(p1) != make_cache_key(p2)


# --- L1 in-memory cache -------------------------------------------------------

def test_l1_hit_and_miss():
    cache = _ExpiringLRU(max_entries=8, ttl_seconds=60)
    assert cache.get("k") is None
    cache.set("k", {"x": 1})
    assert cache.get("k") == {"x": 1}


def test_l1_ttl_expiry():
    cache = _ExpiringLRU(max_entries=8, ttl_seconds=0.05)
    cache.set("k", 1)
    time.sleep(0.08)
    assert cache.get("k") is None


def test_l1_disabled_when_ttl_zero():
    cache = _ExpiringLRU(max_entries=8, ttl_seconds=0)
    cache.set("k", 1)
    assert cache.get("k") is None


def test_l1_lru_eviction():
    cache = _ExpiringLRU(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # evicts "a"
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


# --- L2 SQLite round-trip -----------------------------------------------------

class _FakeResponse:
    def __init__(self, content="ok", model="x"):
        self.choices = [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]
        self.model = model
        self.id = "resp_1"
        self.usage = {}


def test_l2_round_trip():
    with tempfile.TemporaryDirectory() as d:
        c = LLMCache(db_path=str(Path(d) / "cache.db"), l1_ttl_seconds=0, l2_ttl_seconds=3600)
        payload = {"model": "x", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 100}
        resp = _FakeResponse(content="hi")
        assert c.get(payload) is None
        c.put(payload, resp)
        out = c.get(payload)
        assert out is not None
        # Hit counters bump on second read
        c.get(payload)
        s = c.stats()
        assert s["miss"] == 1
        assert s["writes"] == 1
        assert s["l2_hit"] >= 1


def test_stream_skips_cache():
    with tempfile.TemporaryDirectory() as d:
        c = LLMCache(db_path=str(Path(d) / "cache.db"), l1_ttl_seconds=0, l2_ttl_seconds=3600)
        payload = {
            "model": "x",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "max_tokens": 50,
        }
        assert c.get(payload) is None
        c.put(payload, _FakeResponse(content="streamed"))
        assert c.get(payload) is None  # streaming never cached
        s = c.stats()
        assert s["skipped"] == 1


def test_l2_ttl_expiry():
    with tempfile.TemporaryDirectory() as d:
        c = LLMCache(db_path=str(Path(d) / "cache.db"), l1_ttl_seconds=0, l2_ttl_seconds=0.05)
        payload = {"model": "x", "messages": [{"role": "user", "content": "hi"}]}
        c.put(payload, _FakeResponse(content="ok"))
        assert c.get(payload) is not None
        time.sleep(0.08)
        assert c.get(payload) is None


# --- Factory: provider detection + marker injection --------------------------

def test_detect_provider_family_anthropic():
    assert detect_provider_family("claude-3-5-sonnet", "") == "anthropic"
    assert detect_provider_family("anthropic.claude-3", "") == "anthropic"


def test_detect_provider_family_gemini():
    assert detect_provider_family("gemini-1.5-pro", "") == "gemini"


def test_detect_provider_family_openai_default():
    assert detect_provider_family("MiniMax-M3", "https://api.minimaxi.com/v1") == "openai"


def test_anthropic_markers_inject_cache_control():
    msgs = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
    ]
    out, _, _ = apply_provider_cache_markers(
        msgs, model="claude-3-5-sonnet", cache_retention="long"
    )
    assert out[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert out[-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_anthropic_retention_none_disables_markers():
    msgs = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]
    out, _, _ = apply_provider_cache_markers(msgs, model="claude-3-5-sonnet", cache_retention="none")
    assert "cache_control" not in out[0]
    assert "cache_control" not in out[-1]


def test_openai_provider_no_markers_by_default():
    msgs = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]
    out, _, body = apply_provider_cache_markers(
        msgs, model="MiniMax-M3", base_url="https://api.minimaxi.com/v1", cache_retention="short"
    )
    assert out == msgs
    assert body == {}


# --- Factory: cached_chat_completion drop-in ---------------------------------

def test_cached_chat_completion_miss_then_hit():
    reset_clients()
    with tempfile.TemporaryDirectory() as d:
        from src.utils.config import get_config
        cfg = get_config()
        original_db = cfg._settings.get("llm", {}).get("cache", {}).get("db_path")
        cfg._settings.setdefault("llm", {}).setdefault("cache", {})["db_path"] = str(Path(d) / "cache.db")
        cfg._settings["llm"]["cache"]["l1_ttl_seconds"] = 60
        cfg._settings["llm"]["cache"]["l2_ttl_seconds"] = 3600
        try:
            from src.utils import llm_cache
            llm_cache._DEFAULT_CACHE = None
            from src.utils import llm_factory
            llm_factory._CLIENTS.clear()

            fake_client = MagicMock()
            resp_obj = _FakeResponse(content="hello world")
            fake_client.chat.completions.create.return_value = resp_obj

            payload = {
                "model": "MiniMax-M3",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 50,
            }
            out1 = cached_chat_completion(fake_client, **payload)
            assert out1.choices[0].message.content == "hello world"
            assert fake_client.chat.completions.create.call_count == 1

            # Second call hits the cache (write + read = +1 cache call, no real call)
            out2 = cached_chat_completion(fake_client, **payload)
            assert out2.choices[0].message.content == "hello world"
            assert fake_client.chat.completions.create.call_count == 1
        finally:
            if original_db is not None:
                cfg._settings["llm"]["cache"]["db_path"] = original_db
            from src.utils import llm_cache
            llm_cache._DEFAULT_CACHE = None
            reset_clients()


def test_cached_chat_completion_stream_always_real_call():
    reset_clients()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([])

    out = cached_chat_completion(
        fake_client,
        model="x",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )
    # streaming call passes straight through to the underlying API
    assert fake_client.chat.completions.create.call_count == 1
