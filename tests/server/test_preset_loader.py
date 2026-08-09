# SPDX-License-Identifier: Apache-2.0
"""Tests for the LLM provider preset loader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.providers.llm.presets import (
    get_preset_by_id,
    load_presets,
    validate_preset,
)

PRESETS_PATH = Path("data/presets/llm-providers.json")


def test_25_presets_load():
    presets = load_presets(PRESETS_PATH)
    assert len(presets) == 25


def test_preset_schema_no_default_model_field():
    """Per B-D1: presets must never contain any model string."""
    presets = load_presets(PRESETS_PATH)
    for p in presets:
        assert "default_model" not in p, f"preset {p['id']} has default_model"
        assert "hardcoded_models" not in p, f"preset {p['id']} has hardcoded_models"
        assert "models" not in p, f"preset {p['id']} has models"


def test_preset_anthropic_no_model_endpoint():
    presets = load_presets(PRESETS_PATH)
    anthropic = get_preset_by_id(presets, "anthropic")
    assert anthropic["model_list_url_suffix"] is None
    assert anthropic["test_url_suffix"] is None
    assert anthropic["family"] == "anthropic"


def test_preset_google_deferred():
    presets = load_presets(PRESETS_PATH)
    google = get_preset_by_id(presets, "google")
    assert google["deferred"] is True
    assert google["family"] == "google"


def test_get_preset_by_id_missing_returns_none():
    presets = load_presets(PRESETS_PATH)
    assert get_preset_by_id(presets, "nonexistent") is None


def test_validate_preset_rejects_unknown_family():
    bad = {
        "id": "x", "label": "X", "family": "unknown_family",
        "default_base_url": "https://x.com", "default_headers": {},
        "api_key_required": True, "api_key_env": None,
        "model_list_url_suffix": "/models", "test_url_suffix": "/models",
        "deferred": False, "icon": "x", "homepage": "https://x.com", "order": 99,
    }
    with pytest.raises(ValueError, match="family"):
        validate_preset(bad)


def test_validate_preset_requires_id_and_label():
    bad = {
        "id": "", "label": "X", "family": "openai_compat",
        "default_base_url": "https://x.com", "default_headers": {},
        "api_key_required": True, "api_key_env": None,
        "model_list_url_suffix": "/models", "test_url_suffix": "/models",
        "deferred": False, "icon": "x", "homepage": "https://x.com", "order": 99,
    }
    with pytest.raises(ValueError, match="id"):
        validate_preset(bad)
