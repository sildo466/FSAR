"""FSAR custom ChromaDB embedding function — calls the OpenAI embeddings API.

Wraps `POST https://api.openai.com/v1/embeddings` (OpenAI-compatible, but uses
an `Authorization: Bearer ...` header). Mirrors the LM Studio adapter shape so
the factory in `src/memory/embedder.py` can dispatch to it identically.

Config resolution (priority high→low):
1. `__init__` args
2. `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_EMBED_MODEL` env vars
3. Defaults: base_url=https://api.openai.com/v1, model=text-embedding-3-small,
   api_key loaded lazily on first call (no default — openai auth is required).
"""

from __future__ import annotations

import os
from typing import List

import httpx

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class OpenAIEmbeddingFunction(EmbeddingFunction[Documents]):
    """Calls OpenAI's `/v1/embeddings` endpoint (also works for OpenAI-compatible providers)."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = (
            model
            or os.environ.get("OPENAI_EMBED_MODEL")
            or self.DEFAULT_MODEL
        )
        self.timeout = timeout
        self._dim: int | None = None

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        if not self.api_key:
            raise RuntimeError("OpenAI embedding requires an api_key (set memory.embedder.api_key)")
        try:
            from src.skills.egress import enforce_url
            from src.utils.config import get_config
            enforce_url(f"{self.base_url}/embeddings", get_config())
            resp = httpx.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": list(input), "model": self.model},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(
                f"OpenAI embedding failed ({self.base_url}, model={self.model}): {e}"
            ) from e

        data = resp.json().get("data", [])
        if not data:
            raise RuntimeError("OpenAI returned empty embeddings")

        data_sorted = sorted(data, key=lambda x: x.get("index", 0))
        embeddings = [d["embedding"] for d in data_sorted]
        if self._dim is None and embeddings:
            self._dim = len(embeddings[0])
        return embeddings

    @staticmethod
    def name() -> str:
        return "openai"

    def default_space(self):  # type: ignore[no-untyped-def]
        from chromadb.api.types import Space
        return Space.COSINE

    @staticmethod
    def build_from_config(config: dict) -> "OpenAIEmbeddingFunction":
        return OpenAIEmbeddingFunction(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model=config.get("model"),
            timeout=float(config.get("timeout", 10.0)),
        )

    def get_config(self) -> dict:
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
        }

    @staticmethod
    def validate_config(config: dict) -> None:
        if not config.get("api_key"):
            raise ValueError("OpenAI embedder requires api_key in memory.embedder.api_key")
