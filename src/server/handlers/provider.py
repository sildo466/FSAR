# SPDX-License-Identifier: MIT
"""Provider WS handler: list_presets, create_builtin, test_connection, fetch_models."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import WebSocket

from src.providers.llm.presets import get_preset_by_id, load_presets
from src.utils.fsar_config import FsarConfig

logger = logging.getLogger(__name__)

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
                pricing=msg.get("pricing"),
                fmt=msg.get("format", ""),
            )
            await ws.send_json(result)
        except ValueError as e:
            await ws.send_json({"type": "provider.error", "code": "bad_request", "message": str(e)})
        return True
    if t == "provider.test_connection":
        result = await provider_test_connection(
            preset_id=msg.get("preset_id", ""),
            base_url=msg.get("base_url", ""),
            api_key=msg.get("api_key", ""),
            model=msg.get("model", ""),
        )
        await ws.send_json(result)
        return True
    if t == "provider.fetch_models":
        result = await provider_fetch_models(
            preset_id=msg.get("preset_id", ""),
            base_url=msg.get("base_url", ""),
            api_key=msg.get("api_key", ""),
        )
        await ws.send_json(result)
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
    pricing: dict | None = None,
    fmt: str = "",
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

    providers = list(fsar_config.get("llm.providers", []) or [])
    active_id = fsar_config.get("llm.active", "")
    target_index = next(
        (i for i, provider in enumerate(providers) if provider.get("id") == active_id),
        None,
    )
    if target_index is None:
        target_index = next(
            (
                i for i, provider in enumerate(providers)
                if provider.get("preset_id") == preset_id
                and str(provider.get("base_url", "")).rstrip("/") == base_url.rstrip("/")
                and provider.get("model") == model
            ),
            None,
        )

    if target_index is None:
        existing_ids = {provider.get("id") for provider in providers}
        suffix = 1
        while f"{preset_id}-{suffix}" in existing_ids:
            suffix += 1
        provider_id = f"{preset_id}-{suffix}"
        created_at = _now_iso()
    else:
        provider_id = str(providers[target_index].get("id"))
        created_at = providers[target_index].get("created_at") or _now_iso()

    now = _now_iso()
    provider_row = {
        "id": provider_id,
        "preset_id": preset_id,
        "label": label or preset["label"],
        "base_url": base_url.rstrip("/"),
        "api_key": api_key or "",
        "model": model.strip(),
        "family": preset["family"],  # B-D5: server-derived, not user-editable
        "enabled": True,
        "created_at": created_at,
        "updated_at": now,
    }
    if fmt:
        provider_row["format"] = fmt
    if pricing:
        provider_row["pricing"] = {
            "input_per_1m": float(pricing.get("input_per_1m", 0) or 0),
            "output_per_1m": float(pricing.get("output_per_1m", 0) or 0),
        }
    if target_index is None:
        providers.append(provider_row)
    else:
        providers[target_index] = provider_row

    deduplicated = [provider_row]
    seen = {_provider_signature(provider_row)}
    for provider in providers:
        if provider.get("id") == provider_id:
            continue
        signature = _provider_signature(provider)
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(provider)

    fsar_config.patch("llm.providers", deduplicated)
    fsar_config.patch("llm.active", provider_id)
    fsar_config.save()
    return {
        "type": "provider.created",
        "provider": provider_row,
        "providers": deduplicated,
        "active": provider_id,
    }


def _provider_signature(provider: dict) -> tuple[str, str, str, str]:
    return (
        str(provider.get("preset_id", "")),
        str(provider.get("base_url", "")).rstrip("/"),
        str(provider.get("model", "")),
        str(provider.get("api_key", "")),
    )


async def provider_test_connection(
    preset_id: str, base_url: str, api_key: str, model: str,
) -> dict:
    """Probe a vendor's endpoint to verify reachability + auth + model.

    Returns one of: ok / unreachable / auth_failed / bad_request /
    model_required / deferred / unknown. Uses user-typed model for anthropic.
    """
    presets = load_presets(_PRESETS_PATH)
    preset = get_preset_by_id(presets, preset_id)
    if preset is None:
        return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": None}
    if preset.get("deferred"):
        return {"type": "provider.test_result", "ok": False, "error": "deferred", "latency_ms": None}

    family = preset["family"]
    started = datetime.now(timezone.utc)

    try:
        if family == "openai_compat":
            return await _test_openai_compat(base_url, api_key, started)
        elif family == "anthropic":
            if not model or not model.strip():
                return {"type": "provider.test_result", "ok": False, "error": "model_required", "latency_ms": None}
            return await _test_anthropic(base_url, api_key, model, preset.get("default_headers", {}), started)
        else:
            return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": None}
    except Exception as e:
        logger.warning("test_connection unexpected error: %s", e)
        return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": None}


async def _test_openai_compat(base_url: str, api_key: str, started: datetime) -> dict:
    url = base_url.rstrip("/") + "/models"
    from src.skills.egress import enforce_url
    from src.utils.config import get_config
    enforce_url(url, get_config())
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        try:
            r = await client.get(url, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
            return {"type": "provider.test_result", "ok": False, "error": "unreachable",
                    "latency_ms": _elapsed_ms(started)}
    latency = _elapsed_ms(started)
    if r.status_code in (200,):
        return {"type": "provider.test_result", "ok": True, "error": None, "latency_ms": latency}
    if r.status_code in (401, 403):
        return {"type": "provider.test_result", "ok": False, "error": "auth_failed", "latency_ms": latency}
    return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": latency}


async def _test_anthropic(
    base_url: str, api_key: str, model: str, default_headers: dict, started: datetime,
) -> dict:
    url = base_url.rstrip("/") + "/messages"
    from src.skills.egress import enforce_url
    from src.utils.config import get_config
    enforce_url(url, get_config())
    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": default_headers.get("anthropic-version", "2023-06-01"),
    }
    body = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        try:
            r = await client.post(url, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
            return {"type": "provider.test_result", "ok": False, "error": "unreachable",
                    "latency_ms": _elapsed_ms(started)}
    latency = _elapsed_ms(started)
    if r.status_code in (200, 400):
        return {"type": "provider.test_result", "ok": True, "error": None, "latency_ms": latency}
    if r.status_code in (401, 403):
        return {"type": "provider.test_result", "ok": False, "error": "auth_failed", "latency_ms": latency}
    if r.status_code in (404, 405):
        return {"type": "provider.test_result", "ok": False, "error": "bad_request", "latency_ms": latency}
    return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": latency}


def _elapsed_ms(started: datetime) -> int:
    return int((datetime.now(timezone.utc) - started).total_seconds() * 1000)


async def provider_fetch_models(preset_id: str, base_url: str, api_key: str) -> dict:
    """GET {base_url}{model_list_url_suffix}; return list of model ids."""
    presets = load_presets(_PRESETS_PATH)
    preset = get_preset_by_id(presets, preset_id)
    if preset is None or preset.get("model_list_url_suffix") is None:
        return {"type": "provider.models", "ok": False, "models": [], "error": "no_model_list_endpoint"}
    url = base_url.rstrip("/") + preset["model_list_url_suffix"]
    from src.skills.egress import enforce_url
    from src.utils.config import get_config
    enforce_url(url, get_config())
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            r = await client.get(url, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
        return {"type": "provider.models", "ok": False, "models": [], "error": "unreachable"}
    if r.status_code != 200:
        return {"type": "provider.models", "ok": False, "models": [], "error": f"http_{r.status_code}"}
    data = r.json()
    models = []
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        for m in data["data"]:
            if isinstance(m, dict) and "id" in m:
                models.append(m["id"])
            elif isinstance(m, str):
                models.append(m)
    elif isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and "id" in m:
                models.append(m["id"])
            elif isinstance(m, str):
                models.append(m)
    elif isinstance(data, dict) and isinstance(data.get("models"), list):
        for m in data["models"]:
            if isinstance(m, dict) and "name" in m:
                models.append(m["name"])
            elif isinstance(m, str):
                models.append(m)
    return {"type": "provider.models", "ok": True, "models": models, "error": None}
