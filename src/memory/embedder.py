"""FSAR Embedder 工厂 — 根据配置选择 LM Studio 或 Ollama.

读取顺序 (高 → 低):
1. settings.yaml  -> memory.embedder.{provider,base_url,model}
2. 环境变量       -> EMBED_PROVIDER / EMBED_BASE_URL / EMBED_MODEL
3. 默认值         -> lmstudio / http://192.168.5.71:1234 / text-embedding-embeddinggemma-300m-qat

provider 可选: "lmstudio" | "ollama"
"""

from __future__ import annotations

import os
from typing import Any

from src.utils.config import get_config
from src.utils.logger import logger


PROVIDERS = ("lmstudio", "ollama")


def build_embedder(provider: str | None = None,
                   base_url: str | None = None,
                   model: str | None = None,
                   timeout: float | None = None):
    """构造一个 ChromaDB 兼容的 EmbeddingFunction.

    不传参数时从 settings.yaml + 环境变量 + 默认值依次 fallback。
    """
    cfg = get_config()
    emb_cfg = (cfg.get("memory.embedder") or {}) if hasattr(cfg, "get") else {}

    p = (provider
         or emb_cfg.get("provider")
         or os.environ.get("EMBED_PROVIDER")
         or "lmstudio").lower()

    if p not in PROVIDERS:
        raise ValueError(f"未知 embedder provider: {p!r}（可选: {PROVIDERS}）")

    timeout = timeout or float(emb_cfg.get("timeout", 60.0))

    if p == "lmstudio":
        from src.memory.lmstudio_embed import LMStudioEmbeddingFunction
        return LMStudioEmbeddingFunction(
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
    if p == "ollama":
        from src.memory.ollama_embed import OllamaEmbeddingFunction
        return OllamaEmbeddingFunction(
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
    # 不会到这里
    raise AssertionError(f"unreachable: {p}")


def probe(provider: str | None = None) -> dict[str, Any]:
    """快速探测当前 embedder 是否可用，返回 {ok, provider, base_url, model, dim?, error?}."""
    try:
        ef = build_embedder(provider=provider)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    info: dict[str, Any] = {
        "ok": False,
        "provider": ef.__class__.__name__,
        "base_url": getattr(ef, "base_url", ""),
        "model": getattr(ef, "model", ""),
    }
    try:
        vecs = ef(["ping"])
        if vecs and len(vecs) > 0 and len(vecs[0]) > 0:
            info["ok"] = True
            info["dim"] = len(vecs[0])
    except Exception as e:
        info["error"] = str(e)
    return info