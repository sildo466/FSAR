# SPDX-License-Identifier: MIT
"""The agent loop's scope comes from its caller, not from the engine.

A room runs several characters at once in one engine. The engine's `_cancelled`
flag, its `_session_tier_override` and the short cache for a conversation are
all process-wide, so a room turn that used them would cancel, retarget or read
the history of whatever else is running.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.server.chat_engine import ChatEngine


def _engine(**attrs) -> ChatEngine:
    """No __init__: these two helpers read nothing but what is set here."""
    engine = ChatEngine.__new__(ChatEngine)
    engine._cancelled = False
    engine._session_tier_override = None
    engine._short_cache = {}
    engine.config = SimpleNamespace(get=lambda path, default=None: default)
    for name, value in attrs.items():
        setattr(engine, name, value)
    return engine


# --- _agent_scope -----------------------------------------------------------


def test_the_tier_override_wins_over_the_session_override() -> None:
    engine = _engine(_session_tier_override="low")
    _stop, profile = engine._agent_scope(should_stop=None, tier_override="xhigh")
    assert profile.name == "xhigh"
    # Whoever else is running keeps their own tier.
    assert engine._session_tier_override == "low"


def test_the_session_override_is_still_the_default() -> None:
    engine = _engine(_session_tier_override="high")
    _stop, profile = engine._agent_scope(should_stop=None, tier_override=None)
    assert profile.name == "high"


def test_the_configured_tier_is_the_last_resort() -> None:
    engine = _engine()
    engine.config = SimpleNamespace(get=lambda path, default=None: "low")
    _stop, profile = engine._agent_scope(should_stop=None, tier_override=None)
    assert profile.name == "low"


def test_the_stop_predicate_is_the_callers_when_given() -> None:
    """Cancelling one room must not stop the chat page's turn in another
    conversation — which is what a shared engine-wide flag does."""
    engine = _engine()
    called: list[int] = []

    def stop() -> bool:
        called.append(1)
        return True

    resolved, _profile = engine._agent_scope(should_stop=stop, tier_override=None)
    assert resolved() is True
    assert called == [1]


def test_the_stop_predicate_is_the_engines_flag_when_not_given() -> None:
    engine = _engine(_cancelled=True)
    resolved, _profile = engine._agent_scope(should_stop=None, tier_override=None)
    assert resolved() is True
    engine._cancelled = False
    assert resolved() is False


# --- _agent_messages --------------------------------------------------------


def test_a_caller_supplied_history_replaces_the_short_cache() -> None:
    """A room's history lives in the session store, not the short cache. Read
    from the wrong place and the character answers a conversation it never saw."""
    engine = _engine()
    engine._short_cache = {"s1": [{"role": "user", "content": "from the cache"}]}
    hydrated: list[str] = []
    engine._ensure_short = hydrated.append
    engine._fit_history = lambda sp, hist, cw, mo: list(hist)

    messages = engine._agent_messages(
        "sys", "s1", [{"role": "user", "content": "from the room"}],
        128000, 4096,
    )
    assert messages == [{"role": "user", "content": "from the room"}]
    assert hydrated == [], "the short cache was not consulted"


def test_the_short_cache_is_the_source_by_default() -> None:
    engine = _engine()
    engine._short_cache = {"s1": [{"role": "user", "content": "from the cache"}]}
    hydrated: list[str] = []
    engine._ensure_short = hydrated.append
    engine._fit_history = lambda sp, hist, cw, mo: list(hist)

    messages = engine._agent_messages("sys", "s1", None, 128000, 4096)
    assert messages == [{"role": "user", "content": "from the cache"}]
    assert hydrated == ["s1"]
