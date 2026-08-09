# SPDX-License-Identifier: MIT
"""LLM provider preset loader and validator."""
from __future__ import annotations

import json
from pathlib import Path

_VALID_FAMILIES = {"openai_compat", "anthropic", "google"}
_REQUIRED_FIELDS = {
    "id", "label", "family", "default_base_url", "default_headers",
    "api_key_required", "model_list_url_suffix", "test_url_suffix",
    "deferred", "icon", "order",
}
_FORBIDDEN_MODEL_FIELDS = {"default_model", "hardcoded_models", "models"}


def load_presets(path: Path) -> list[dict]:
    """Load and validate the LLM vendor preset list from JSON."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"preset file must be a JSON array, got {type(data).__name__}")
    for p in data:
        validate_preset(p)
    return data


def validate_preset(p: dict) -> None:
    """Validate one preset; raise ValueError on violation."""
    missing = _REQUIRED_FIELDS - set(p.keys())
    if missing:
        raise ValueError(f"preset missing fields: {missing}")
    if not p["id"] or not p["label"]:
        raise ValueError(f"preset requires non-empty id and label")
    if p["family"] not in _VALID_FAMILIES:
        raise ValueError(f"preset {p['id']}: family must be one of {_VALID_FAMILIES}, got {p['family']!r}")
    # deferred is a generic provider-availability flag; specific families do not get special handling
    forbidden = _FORBIDDEN_MODEL_FIELDS & set(p.keys())
    if forbidden:
        raise ValueError(f"preset {p['id']} must not contain model fields: {forbidden}")
    if not isinstance(p["order"], int):
        raise ValueError(f"preset {p['id']}: order must be int")


def get_preset_by_id(presets: list[dict], preset_id: str) -> dict | None:
    for p in presets:
        if p["id"] == preset_id:
            return p
    return None
