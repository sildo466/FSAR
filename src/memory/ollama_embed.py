"""FSAR 自定义 ChromaDB embedding 函数 — 调用本地 Ollama 服务.

Ollama 提供 /api/embeddings 接口 (POST):
  {"model": "...", "prompt": "..."}  → {"embedding": [...]}

注意：每次只接受一个 prompt（不像 LM Studio 接受 batch）。
默认地址: http://localhost:11434
"""

from __future__ import annotations

import os
from typing import List

import httpx

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """调用本地 Ollama /api/embeddings 接口.

    配置来源 (优先级 高→低):
    1. __init__ 参数
    2. 环境变量 OLLAMA_BASE_URL / OLLAMA_EMBED_MODEL
    3. 默认值: http://localhost:11434 / nomic-embed-text
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "nomic-embed-text"

    def __init__(self,
                 base_url: str | None = None,
                 model: str | None = None,
                 timeout: float = 10.0):
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = (
            model
            or os.environ.get("OLLAMA_EMBED_MODEL")
            or self.DEFAULT_MODEL
        )
        self.timeout = timeout

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        embeddings: Embeddings = []
        # Ollama 一次只接受一个 prompt，循环调用
        for text in input:
            try:
                from src.skills.egress import enforce_url
                from src.utils.config import get_config
                enforce_url(f"{self.base_url}/api/embeddings", get_config())
                resp = httpx.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except Exception as e:
                raise RuntimeError(
                    f"Ollama embedding 调用失败 ({self.base_url}, "
                    f"model={self.model}): {e}"
                ) from e
            data = resp.json()
            vec = data.get("embedding")
            if not vec:
                raise RuntimeError(f"Ollama 返回空 embedding: {data}")
            embeddings.append(vec)
        return embeddings

    @staticmethod
    def name() -> str:
        return "ollama"

    def default_space(self):  # type: ignore[no-untyped-def]
        from chromadb.api.types import Space
        return Space.COSINE

    @staticmethod
    def build_from_config(config: dict) -> "OllamaEmbeddingFunction":
        return OllamaEmbeddingFunction(
            base_url=config.get("base_url"),
            model=config.get("model"),
            timeout=float(config.get("timeout", 10.0)),
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
