# SPDX-License-Identifier: MIT
"""ASR preset loader and validator tests."""

from pathlib import Path

import pytest

from src.providers.asr.presets import get_preset_by_id, load_presets, validate_preset


def test_load_presets_returns_three_entries():
    presets = load_presets(Path("data/presets/asr-providers.json"))
    assert len(presets) == 3


def test_preset_ids_are_unique():
    presets = load_presets(Path("data/presets/asr-providers.json"))
    ids = [preset["id"] for preset in presets]
    assert len(ids) == len(set(ids))


def test_forbidden_default_fields_absent():
    presets = load_presets(Path("data/presets/asr-providers.json"))
    for preset in presets:
        assert "default_model" not in preset
        assert "default_language" not in preset


def test_family_is_valid():
    presets = load_presets(Path("data/presets/asr-providers.json"))
    for preset in presets:
        assert preset["family"] in {"local", "openai_compat", "volcengine"}


def test_faster_whisper_is_local_no_key():
    presets = load_presets(Path("data/presets/asr-providers.json"))
    preset = get_preset_by_id(presets, "faster-whisper")
    assert preset is not None
    assert preset["family"] == "local"
    assert preset["api_key_required"] is False


def test_volcengine_deferred():
    presets = load_presets(Path("data/presets/asr-providers.json"))
    preset = get_preset_by_id(presets, "volcengine-asr")
    assert preset is not None
    assert preset["deferred"] is True


def test_validate_preset_rejects_default_model():
    with pytest.raises(ValueError, match="must not contain default_model"):
        validate_preset(
            {
                "id": "test",
                "label": "Test",
                "family": "local",
                "api_key_required": False,
                "deferred": False,
                "icon": "test",
                "order": 99,
                "default_model": "x",
            }
        )
