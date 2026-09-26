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


class _FakeGuard:
    """Mirrors `list_quarantine()`: quarantined rows only, restored ones absent."""

    def __init__(self, rows):
        self._rows = rows

    def list_quarantine(self):
        return self._rows


def _patch_guard(monkeypatch, rows):
    import src.server.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_get_content_guard", lambda: _FakeGuard(rows))


async def _create_character(websocket, db, name: str) -> int:
    await card_handler.dispatch(
        websocket,
        {"type": "card.upsert", "kind": "character", "card": {"name": name, "description": name}},
        {"db_path": str(db)},
    )
    return websocket.send_json.call_args.args[0]["id"]


async def _listed_names(websocket, db) -> list[str]:
    await card_handler.dispatch(
        websocket, {"type": "card.list", "kind": "character"}, {"db_path": str(db)}
    )
    return [c["name"] for c in websocket.send_json.call_args.args[0]["cards"]]


@pytest.mark.anyio
async def test_list_hides_a_quarantined_character_card(tmp_path, monkeypatch):
    """A screened card keeps its row (sessions reference the id) but its fields
    are blanked, so listing it would offer an empty character."""
    db = tmp_path / "memory.db"
    websocket = AsyncMock()
    kept = await _create_character(websocket, db, "Keeper")
    hidden = await _create_character(websocket, db, "REDTEAM-EXFIL")
    _patch_guard(
        monkeypatch,
        [{"store": "card", "record_ref": str(hidden), "state": "quarantined"}],
    )

    assert await _listed_names(websocket, db) == ["Keeper"]
    assert kept != hidden


@pytest.mark.anyio
async def test_restored_cards_reappear(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    websocket = AsyncMock()
    await _create_character(websocket, db, "Restored")
    # a restored card is not returned by list_quarantine() at all
    _patch_guard(monkeypatch, [])

    assert await _listed_names(websocket, db) == ["Restored"]


@pytest.mark.anyio
async def test_other_stores_do_not_hide_cards(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    websocket = AsyncMock()
    await _create_character(websocket, db, "Keeper")
    _patch_guard(
        monkeypatch,
        [{"store": "chunk", "record_ref": "1", "state": "quarantined"}],
    )

    assert await _listed_names(websocket, db) == ["Keeper"]


@pytest.mark.anyio
async def test_a_malformed_record_ref_does_not_break_the_list(tmp_path, monkeypatch):
    """record_ref is stored as text, so a hand-edited row must not take the
    whole card list down with it."""
    db = tmp_path / "memory.db"
    websocket = AsyncMock()
    await _create_character(websocket, db, "Keeper")
    _patch_guard(
        monkeypatch,
        [{"store": "card", "record_ref": "not-an-id", "state": "quarantined"}],
    )

    assert await _listed_names(websocket, db) == ["Keeper"]
