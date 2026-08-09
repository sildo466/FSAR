"""FSAR 自定义 ChromaDB embedding 函数 — 调用 LM Studio 本地 embedding API.

替代默认的 ONNX MiniLM（需要 HTTPS 下载），走本地 LM Studio 的 OpenAI 兼容接口。
默认地址: http://192.168.5.71:1234  (LM Studio 默认端口)
"""

from __future__ import annotations

import os
from typing import List

import httpx

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class LMStudioEmbeddingFunction(EmbeddingFunction[Documents]):
    """调用 LM Studio OpenAI 兼容 /v1/embeddings 接口.

    配置来源 (优先级 高→低):
    1. __init__ 参数
    2. 环境变量 LMSTUDIO_BASE_URL / LMSTUDIO_EMBED_MODEL
    3. 默认值: http://192.168.5.71:1234 / text-embedding-embeddinggemma-300m-qat
    """

    DEFAULT_BASE_URL = "http://192.168.5.71:1234"
    DEFAULT_MODEL = "text-embedding-embeddinggemma-300m-qat"

    def __init__(self,
                 base_url: str | None = None,
                 model: str | None = None,
                 timeout: float = 60.0):
        configured_base_url = (
            base_url
            or os.environ.get("LMSTUDIO_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        while configured_base_url.lower().endswith("/v1"):
            configured_base_url = configured_base_url[: -len("/v1")].rstrip("/")
        self.base_url = configured_base_url
        self.model = (
            model
            or os.environ.get("LMSTUDIO_EMBED_MODEL")
            or self.DEFAULT_MODEL
        )
        self.timeout = timeout
        self._dim: int | None = None

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        # LM Studio 的 OpenAI 兼容接口一次接受一组字符串
        try:
            from src.skills.egress import enforce_url
            from src.utils.config import get_config
            enforce_url(f"{self.base_url}/v1/embeddings", get_config())
            resp = httpx.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": list(input), "model": self.model},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(
                f"LM Studio embedding 调用失败 ({self.base_url}): {e}"
            ) from e

        data = resp.json().get("data", [])
        if not data:
            raise RuntimeError("LM Studio 返回空 embeddings")

        # 按 index 排序后取 embedding
        data_sorted = sorted(data, key=lambda x: x.get("index", 0))
        embeddings = [d["embedding"] for d in data_sorted]
        if self._dim is None and embeddings:
            self._dim = len(embeddings[0])
        return embeddings

    @staticmethod
    def name() -> str:
        return "lmstudio"

    def default_space(self):  # type: ignore[no-untyped-def]
        from chromadb.api.types import Space
        return Space.COSINE

    @staticmethod
    def build_from_config(config: dict) -> "LMStudioEmbeddingFunction":
        return LMStudioEmbeddingFunction(
            base_url=config.get("base_url"),
            model=config.get("model"),
            timeout=float(config.get("timeout", 60.0)),
        )

    def get_config(self) -> dict:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
        }

    @staticmethod
    def validate_config(config: dict) -> None:
        pass
