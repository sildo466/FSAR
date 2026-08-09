# SPDX-License-Identifier: MIT
"""TTS preset loader and validator tests."""

from pathlib import Path

import pytest

from src.providers.tts.presets import get_preset_by_id, load_presets, validate_preset


def test_load_presets_returns_eight_entries():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    assert len(presets) == 8


def test_preset_ids_are_unique():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    ids = [preset["id"] for preset in presets]
    assert len(ids) == len(set(ids))


def test_required_fields_present():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    required = {
        "id",
        "label",
        "family",
        "api_key_required",
        "deferred",
        "icon",
        "order",
    }
    for preset in presets:
        missing = required - set(preset)
        assert not missing, f"preset {preset.get('id')} missing {missing}"


def test_forbidden_default_fields_absent():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    for preset in presets:
        assert "default_voice" not in preset
        assert "default_model" not in preset


def test_family_is_valid():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    valid = {
        "edge",
        "openai_compat",
        "elevenlabs",
        "azure",
        "dashscope",
        "volcengine",
        "minimax",
    }
    for preset in presets:
        assert preset["family"] in valid


def test_get_preset_by_id_found():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    preset = get_preset_by_id(presets, "openai")
    assert preset is not None
    assert preset["family"] == "openai_compat"


def test_get_preset_by_id_missing():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    assert get_preset_by_id(presets, "nonexistent") is None


def test_validate_preset_rejects_default_voice():
    with pytest.raises(ValueError, match="must not contain default_voice"):
        validate_preset(
            {
                "id": "test",
                "label": "Test",
                "family": "edge",
                "api_key_required": False,
                "deferred": False,
                "icon": "test",
                "order": 99,
                "default_voice": "x",
            }
        )


def test_qwen_tts_preset_present():
    presets = load_presets(Path("data/presets/tts-providers.json"))
    preset = get_preset_by_id(presets, "qwen-tts")
    assert preset is not None
    assert preset["family"] == "dashscope"
    assert preset["voice_placeholder"] == ""
    assert preset["model_placeholder"] == ""
    assert "Cherry" in preset["voices"]
