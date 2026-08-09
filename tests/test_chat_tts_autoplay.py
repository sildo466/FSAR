# SPDX-License-Identifier: MIT
"""Chat-engine TTS autoplay queue tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.server.chat_engine import ChatEngine
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


def engine(tmp_path, *, active="p1", autoplay=True, card_autoplay=1):
    instance = object.__new__(ChatEngine)
    instance.config = FsarConfig(tmp_path / "config.yaml")
    instance.config.patch("tts.active", active)
    instance.config.patch("tts.autoplay", autoplay)
    instance.session_store = MagicMock()
    instance.session_store.get_character.return_value = 7
    instance.card_repo = MagicMock()
    instance.card_repo.get_character.return_value = SimpleNamespace(
        tts_autoplay_on_card=card_autoplay
    )
    return instance


@pytest.mark.anyio
async def test_queues_tts_when_global_and_character_autoplay_enabled(tmp_path):
    instance = engine(tmp_path)
    websocket = AsyncMock()
    await instance._maybe_queue_tts(
        websocket,
        message_id="msg_1",
        text="Hello from the assistant",
        conversation_id="conv_1",
    )
    websocket.send_json.assert_awaited_once_with(
        {
            "type": "tts.synthesize_queued",
            "message_id": "msg_1",
            "text_preview": "Hello from the assistant",
        }
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("active", "autoplay", "card_autoplay"),
    [("", True, 1), ("p1", False, 1), ("p1", True, 0)],
)
async def test_does_not_queue_when_any_autoplay_gate_is_off(
    tmp_path, active, autoplay, card_autoplay
):
    instance = engine(
        tmp_path,
        active=active,
        autoplay=autoplay,
        card_autoplay=card_autoplay,
    )
    websocket = AsyncMock()
    await instance._maybe_queue_tts(
        websocket,
        message_id="msg_1",
        text="Hello",
        conversation_id="conv_1",
    )
    websocket.send_json.assert_not_awaited()
