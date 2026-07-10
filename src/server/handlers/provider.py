# SPDX-License-Identifier: Apache-2.0
"""Provider WS handler: list_presets, create_builtin, test_connection, fetch_models."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import WebSocket

from src.providers.llm.presets import get_preset_by_id, load_presets
from src.utils.fsar_config import FsarConfig

_PRESETS_PATH = Path("data/presets/llm-providers.json")
_TIMEOUT_S = 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: FsarConfig) -> bool:
    """Route provider.* WS messages. Returns True if handled."""
    t = msg.get("type")
    if t == "provider.list_presets":
        await ws.send_json(await provider_list_presets())
        return True
    if t == "provider.create_builtin":
        try:
            result = await provider_create_builtin(
                fsar_config=config,
                preset_id=msg.get("preset_id", ""),
                label=msg.get("label", ""),
                api_key=msg.get("api_key", ""),
                base_url=msg.get("base_url", ""),
                model=msg.get("model", ""),
            )
            await ws.send_json(result)
        except ValueError as e:
            await ws.send_json({"type": "provider.error", "code": "bad_request", "message": str(e)})
        return True
    return False


async def provider_list_presets() -> dict:
    """Return all 25 built-in vendor presets (B-D1: no models in payload)."""
    presets = load_presets(_PRESETS_PATH)
    return {"type": "provider.presets", "presets": presets}


async def provider_create_builtin(
    fsar_config: FsarConfig,
    preset_id: str,
    label: str,
    api_key: str,
    base_url: str,
    model: str,
) -> dict:
    """Create a provider instance from a preset; write to fsar.yaml atomically."""
    presets = load_presets(_PRESETS_PATH)
    preset = get_preset_by_id(presets, preset_id)
    if preset is None:
        raise ValueError(f"preset not found: {preset_id}")
    if not model or not model.strip():
        raise ValueError("model is required")
    if not base_url or not base_url.strip():
        raise ValueError("base_url is required")

    providers = fsar_config.get("llm.providers", []) or []
    existing_ids = {p.get("id") for p in providers}
    suffix = 1
    while f"{preset_id}-{suffix}" in existing_ids:
        suffix += 1
    new_id = f"{preset_id}-{suffix}"

    now = _now_iso()
    provider_row = {
        "id": new_id,
        "preset_id": preset_id,
        "label": label or preset["label"],
        "base_url": base_url,
        "api_key": api_key or "",
        "model": model,
        "family": preset["family"],  # B-D5: server-derived, not user-editable
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    providers.append(provider_row)
    fsar_config.patch("llm.providers", providers)
    if not fsar_config.get("llm.active"):
        fsar_config.patch("llm.active", new_id)
    fsar_config.save()
    return {"type": "provider.created", "provider": provider_row}
