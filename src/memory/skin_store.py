# SPDX-License-Identifier: MIT
"""Scan data/skins/*/skin.json into plain dicts (P1)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PALETTE_KEYS = frozenset({
    "bg", "surface", "surface2", "text", "textMuted", "textFaint",
    "border", "borderStrong", "glass", "glassStrong", "glassBorder",
    "glowSoft", "glowFaint", "success", "warning", "danger", "accent",
})


def list_skins(base_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(base_dir)
    if not root.is_dir():
        return []
    skins: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        path = entry / "skin.json"
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("skin %s: unreadable skin.json: %s", entry.name, exc)
            continue
        if not isinstance(raw, dict) or raw.get("id") != entry.name or not isinstance(raw.get("name"), str):
            logger.warning("skin %s: bad id or name, skipped", entry.name)
            continue
        base = raw.get("base", "light")
        if base not in {"light", "dark"}:
            base = "light"
        palette_raw = raw.get("palette") or {}
        palette = {
            k: v for k, v in palette_raw.items()
            if isinstance(v, str) and k in _PALETTE_KEYS
        }
        background_raw = raw.get("background") or {}
        background: dict[str, Any] = {}
        if isinstance(background_raw, dict):
            img = background_raw.get("chatImage")
            if isinstance(img, str):
                background["chatImage"] = img
            overlay = background_raw.get("chatOverlay")
            if isinstance(overlay, (int, float)) and not isinstance(overlay, bool):
                background["chatOverlay"] = max(0.0, min(1.0, float(overlay)))
        skins.append({
            "id": entry.name, "name": raw["name"], "base": base,
            "palette": palette, "background": background,
        })
    return skins