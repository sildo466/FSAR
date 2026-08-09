"""WS dispatcher for embedder configuration (save + probe)."""
from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.utils.fsar_config import FsarConfig


def _allowed_provider(p: str) -> bool:
    return p in ("openai", "lmstudio", "ollama")


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: FsarConfig) -> bool:
    """Route embedding.* WS messages. Returns True if handled."""
    t = msg.get("type")

    if t == "embedding.upsert":
        provider = (msg.get("provider") or "").lower()
        base_url = msg.get("base_url") or ""
        model = msg.get("model") or ""
        api_key = msg.get("api_key") or ""
        timeout = msg.get("timeout")

        if not _allowed_provider(provider):
            await ws.send_json({
                "type": "embedding.error",
                "code": "bad_provider",
                "message": f"provider must be one of openai/lmstudio/ollama, got {provider!r}",
            })
            return True

        config.patch("memory.embedder.provider", provider)
        if base_url:
            config.patch("memory.embedder.base_url", base_url)
        if model:
            config.patch("memory.embedder.model", model)
        if api_key:
            config.patch("memory.embedder.api_key", api_key)
        if timeout:
            config.patch("memory.embedder.timeout", float(timeout))
        try:
            config.save()
        except Exception as e:
            await ws.send_json({
                "type": "embedding.error",
                "code": "save_failed",
                "message": str(e),
            })
            return True

        await ws.send_json({
            "type": "embedding.saved",
            "provider": provider,
            "base_url": config.get("memory.embedder.base_url", ""),
            "model": config.get("memory.embedder.model", ""),
        })
        return True

    if t == "embedding.probe":
        provider = (msg.get("provider") or "").lower() or None
        base_url = msg.get("base_url") or None
        model = msg.get("model") or None
        api_key = msg.get("api_key") or None

        try:
            from src.memory.embedder import build_embedder
            ef = build_embedder(
                provider=provider,
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
            vecs = ef(["ping"])
            if not vecs or len(vecs[0]) == 0:
                raise RuntimeError("empty embedding returned")
            await ws.send_json({
                "type": "embedding.probe_result",
                "ok": True,
                "provider": getattr(ef, "name", lambda: provider)(),
                "base_url": getattr(ef, "base_url", ""),
                "model": getattr(ef, "model", ""),
                "dim": len(vecs[0]),
                "error": None,
            })
        except Exception as e:
            await ws.send_json({
                "type": "embedding.probe_result",
                "ok": False,
                "provider": provider,
                "error": str(e),
            })
        return True

    return False
