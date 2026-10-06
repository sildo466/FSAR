# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.memory.skin_store import _PALETTE_KEYS, list_skins

ASSET = Path(__file__).resolve().parents[1] / "assets" / "birthday_skin"


def test_the_json_is_self_consistent_and_light():
    raw = json.loads((ASSET / "skin.json").read_text(encoding="utf-8"))
    assert raw["id"] == "birthday"
    assert raw["base"] == "light"
    assert isinstance(raw["name"], str) and raw["name"]


def test_every_palette_key_is_one_the_store_accepts():
    raw = json.loads((ASSET / "skin.json").read_text(encoding="utf-8"))
    unknown = set(raw.get("palette") or {}) - _PALETTE_KEYS
    assert unknown == set()


def test_it_survives_a_round_trip_through_the_store(tmp_path):
    """The real check: copy it in under the granted name and confirm the store
    reads it back — the folder name and the json id must agree."""
    shutil.copytree(ASSET, tmp_path / "skins" / "birthday")
    skins = list_skins(tmp_path / "skins")
    assert [s["id"] for s in skins] == ["birthday"]
    assert skins[0]["base"] == "light"
    assert skins[0]["palette"].get("bg")
    assert skins[0]["palette"].get("text")
