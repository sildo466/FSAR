from __future__ import annotations

import sqlite3
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import src.server.ws_server as ws_mod
from src.memory.cards import CardRepo, CharacterCard


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), color=(12, 34, 56)).save(output, format="JPEG")
    return output.getvalue()


def test_uploaded_avatar_is_served_from_the_memory_database_directory(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    repo = CardRepo(db_path)
    card_id = repo.upsert_character(CharacterCard(
        id=None,
        name="Avatar Character",
        description="",
        personality="calm",
    ))
    isolated_card_id = 987654
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE character_cards SET id = ? WHERE id = ?",
            (isolated_card_id, card_id),
        )
        connection.commit()
    card_id = isolated_card_id
    monkeypatch.setattr(ws_mod._engine, "card_repo", repo)
    monkeypatch.setitem(ws_mod._ctx, "db_path", str(db_path))

    client = TestClient(ws_mod.app)
    upload = client.post(
        f"/api/card/{card_id}/avatar",
        content=_jpeg_bytes(),
        headers={"X-FSAR-Avatar-Ext": "jpg"},
    )
    response = client.get(f"/api/card/{card_id}/avatar")

    assert upload.status_code == 200
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["cache-control"] == "no-store"
