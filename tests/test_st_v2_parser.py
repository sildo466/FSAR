# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.server.handlers.card import parse_sillytavern_v2


def test_parse_v2_basic():
    json_text = """{
      "spec": "chara_card_v2",
      "spec_version": "2.0",
      "data": {
        "name": "Imported",
        "description": "An imported character",
        "personality": "curious",
        "scenario": "meeting",
        "first_mes": "Hello!",
        "mes_example": "user: hi\\nassistant: hey"
      }
    }"""
    card = parse_sillytavern_v2(json_text)
    assert card.name == "Imported"
    assert card.description == "An imported character"
    assert card.scenario == "meeting"
    assert card.example_dialogues == [{"user": "hi", "assistant": "hey"}]


def test_parse_v1_falls_back():
    json_text = '{"name": "v1char", "description": "old", "personality": "old"}'
    card = parse_sillytavern_v2(json_text)
    assert card.name == "v1char"
    assert "st_v1" in card.tags


def test_parse_v3_falls_back():
    json_text = '{"spec": "chara_card_v3", "data": {"name": "v3char"}}'
    card = parse_sillytavern_v2(json_text)
    assert card.name == "v3char"
    assert "st_v3" in card.tags


def test_parse_data_url_avatar():
    b64 = base64.b64encode(b"\x89PNG fake").decode()
    json_text = f'{{"name": "x", "description": "d", "personality": "p", "avatar": "data:image/png;base64,{b64}"}}'
    card = parse_sillytavern_v2(json_text)
    assert card.avatar_path is None
