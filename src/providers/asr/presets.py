# SPDX-License-Identifier: MIT
"""ASR provider preset loader and validator."""

from __future__ import annotations

import json
from pathlib import Path

_VALID_FAMILIES = {"local", "openai_compat", "volcengine"}
_REQUIRED_FIELDS = {
    "id",
    "label",
    "family",
    "api_key_required",
    "deferred",
    "icon",
    "order",
}
_FORBIDDEN_FIELDS = {"default_model", "default_language"}


def load_presets(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(
            f"preset file must be a JSON array, got {type(data).__name__}"
        )
    for preset in data:
        validate_preset(preset)
    ids = [preset["id"] for preset in data]
    if len(ids) != len(set(ids)):
        raise ValueError("preset ids must be unique")
    return data


def validate_preset(preset: dict) -> None:
    if not isinstance(preset, dict):
        raise ValueError("preset must be an object")
    missing = _REQUIRED_FIELDS - set(preset)
    if missing:
        raise ValueError(f"preset missing fields: {missing}")
    if not preset["id"] or not preset["label"]:
        raise ValueError("preset requires non-empty id and label")
    if preset["family"] not in _VALID_FAMILIES:
        raise ValueError(
            f"preset {preset['id']}: family must be one of {_VALID_FAMILIES}, "
            f"got {preset['family']!r}"
        )
    forbidden = _FORBIDDEN_FIELDS & set(preset)
    if forbidden:
        fields = ", ".join(sorted(forbidden))
        raise ValueError(f"preset {preset['id']} must not contain {fields}")
    if not isinstance(preset["order"], int):
        raise ValueError(f"preset {preset['id']}: order must be int")
    if not isinstance(preset["api_key_required"], bool):
        raise ValueError(f"preset {preset['id']}: api_key_required must be bool")
    if not isinstance(preset["deferred"], bool):
        raise ValueError(f"preset {preset['id']}: deferred must be bool")


def get_preset_by_id(presets: list[dict], preset_id: str) -> dict | None:
    return next((preset for preset in presets if preset["id"] == preset_id), None)
