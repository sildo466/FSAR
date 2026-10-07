# SPDX-License-Identifier: MIT
"""Engine command registry must run against a real ChatEngine.

The other command tests hand in a hand-rolled fake engine that mirrors
main.py's legacy attribute names, which is how /rate, /clear and /history came
to read members ChatEngine never had — and stayed green while the real path
raised. `execute()` swallows those into "Command failed: ...".
"""

from __future__ import annotations

import asyncio

import pytest

from src.server.chat_engine import ChatEngine
from src.server.handlers.commands import execute
from src.server.risk_bridge import RiskBridge
from src.utils.fsar_config import FsarConfig


def _engine(tmp_path, *, recorded_reply: bool = False) -> ChatEngine:
    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    config.save()
    engine = ChatEngine(config, RiskBridge())
    engine.new_conversation()
    if recorded_reply:
        # /rate early-returns unless a reply has been recorded.
        engine._msg_ids["reply-1"] = engine.session_store.append_message(
            conversation_id=engine.active_conversation_id(),
            role="assistant", content="the reply under review",
        )
    return engine


@pytest.mark.parametrize("line", ["/clear", "/history"])
def test_command_survives_a_real_engine(tmp_path, line: str) -> None:
    output = asyncio.run(execute(_engine(tmp_path), line))
    assert "Command failed" not in output, output


def test_rate_survives_a_real_engine(tmp_path) -> None:
    engine = _engine(tmp_path, recorded_reply=True)
    output = asyncio.run(execute(engine, "/rate 5"))
    assert "Command failed" not in output, output
    assert "Rated" in output
