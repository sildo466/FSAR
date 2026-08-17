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
        _ELEMENT_KEYS = {
            "input": {"bg", "border", "text"},
            "button": {"bg", "text", "hover", "image", "imageOpacity"},
            "switch": {"on", "off", "thumb"},
            "chip": {"bg", "border"},
            "card": {"bg", "border", "image", "imageOpacity"},
        }
        elements_raw = raw.get("elements") or {}
        elements: dict[str, Any] = {}
        if isinstance(elements_raw, dict):
            for el, fields_raw in elements_raw.items():
                if el not in _ELEMENT_KEYS or not isinstance(fields_raw, dict):
                    continue
                out: dict[str, Any] = {}
                for k, v in fields_raw.items():
                    if k not in _ELEMENT_KEYS[el]:
                        continue
                    if k == "imageOpacity":
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            out[k] = max(0.0, min(1.0, float(v)))
                    elif isinstance(v, str):
                        out[k] = v
                if out:
                    elements[el] = out

        pattern_raw = raw.get("pattern") or {}
        pattern: dict[str, Any] = {}
        if isinstance(pattern_raw, dict):
            img = pattern_raw.get("image")
            if isinstance(img, str) and img:
                pattern["image"] = img
            op = pattern_raw.get("opacity")
            if isinstance(op, (int, float)) and not isinstance(op, bool):
                pattern["opacity"] = max(0.0, min(1.0, float(op)))
        skins.append({
            "id": entry.name, "name": raw["name"], "base": base,
            "palette": palette, "background": background,
            "elements": elements, "pattern": pattern,
        })
    return skins