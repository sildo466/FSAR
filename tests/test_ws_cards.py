# SPDX-License-Identifier: MIT
"""Card WS handler field passthrough tests."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.memory.cards import CardRepo
from src.server.handlers import card as card_handler


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_upsert_character_passes_tts_instructions(tmp_path):
    websocket = AsyncMock()
    ctx = {"db_path": str(tmp_path / "memory.db")}
    await card_handler.dispatch(
        websocket,
        {
            "type": "card.upsert",
            "kind": "character",
            "card": {
                "name": "Miku",
                "description": "Virtual singer",
                "personality": "Cheerful",
                "tts_instructions": "speak cheerfully",
            },
        },
        ctx,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "card.upserted"
    repo = CardRepo(Path(tmp_path / "memory.db"))
    card = repo.get_character(sent["id"])
    assert card is not None
    assert card.tts_instructions == "speak cheerfully"
