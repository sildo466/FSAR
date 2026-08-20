# SPDX-License-Identifier: MIT
"""Real LLM compaction for TUI /compact -> ChatEngine.compact_conversation."""

from __future__ import annotations

import logging

import pytest

from src.server.chat_engine import ChatEngine
from src.server.risk_bridge import RiskBridge
from src.utils.fsar_config import get_default_config

logging.disable(logging.CRITICAL)


@pytest.mark.asyncio
async def test_compact_conversation_summarizes_and_persists() -> None:
    """Older messages are folded into a system checkpoint, tail kept verbatim,
    and history shrank."""
    engine = ChatEngine(get_default_config(), RiskBridge())
    cid = engine.new_conversation()
    for i in range(10):
        engine.session_store.append_message(
            conversation_id=cid, role="user", content=f"user message {i} " + "x" * 200)
        engine.session_store.append_message(
            conversation_id=cid, role="assistant", content=f"assistant reply {i} " + "y" * 200)

    # Reuse the engine's real summarizer seam, but avoid a live LLM call.
    engine.client_and_model = lambda: (object(), "fake-model", "fake-provider")

    async def fake_summarize(*, transcript, **kwargs):
        return "A compact summary of the earlier conversation."

    engine._summarize_context_chunk = fake_summarize

    before, after, compacted = await engine.compact_conversation(cid)
    assert compacted is True
    assert after < before

    rows = engine.session_store.get_session_messages(cid)
    assert rows[0].role == "system", "first message should be the checkpoint"
    assert "[compacted summary]" in (rows[0].content or "")


@pytest.mark.asyncio
async def test_compact_conversation_no_provider() -> None:
    """Without a provider it must no-op, not raise."""
    engine = ChatEngine(get_default_config(), RiskBridge())
    cid = engine.new_conversation()
    for i in range(8):
        engine.session_store.append_message(conversation_id=cid, role="user",
                                            content="u" * 100)
        engine.session_store.append_message(conversation_id=cid, role="assistant",
                                            content="a" * 100)
    engine.client_and_model = lambda: (None, None, None)
    before, after, compacted = await engine.compact_conversation(cid)
    assert compacted is False and before == 0 and after == 0
