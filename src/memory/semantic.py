"""FSAR 语义记忆 — ChromaDB 向量库.

存储对话/事件的语义向量，用于"找相似"召回。
依赖 chromadb；首次运行会下载默认 embedding 模型 (~80MB)。

设计要点:
- 单集合持久化 (data/chroma)
- metadata: session_id, role, ts, tags
- available 属性 — chromadb 不可用时降级为 no-op
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.utils.config import DATA_DIR
from src.utils.logger import logger


@dataclass
class SemanticHit:
    """语义召回的一条结果"""
    text: str
    metadata: dict
    distance: float


class SemanticMemory:
    """ChromaDB-backed semantic memory.

    单集合 'fsar_memory'  — 存所有对话/事件。
    """

    COLLECTION = "fsar_memory"

    def __init__(self, path: str | Path | None = None):
        self._path = Path(path or DATA_DIR / "chroma")
        self._path.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._init()

    def _init(self):
        try:
            import chromadb
            from src.memory.embedder import build_embedder
            self._client = chromadb.PersistentClient(path=str(self._path))
            # 通过工厂选择 embedder (LM Studio / Ollama)
            embedding_fn = build_embedder()
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION,
                embedding_function=embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"Semantic memory initialized at {self._path} "
                        f"(embedder: {embedding_fn.__class__.__name__} "
                        f"/ {getattr(embedding_fn, 'model', '?')} "
                        f"@ {getattr(embedding_fn, 'base_url', '?')})")
        except Exception as e:
            logger.warning(f"Semantic memory unavailable: {e}")
            self._collection = None

    @property
    def available(self) -> bool:
        return self._collection is not None

    def add(self, text: str, *, doc_id: str | None = None,
            session_id: str = "", role: str = "",
            tags: list[str] | None = None,
            metadata: Optional[dict] = None) -> str:
        """添加一条语义记忆。返回 doc_id"""
        if not self.available or not text.strip():
            return ""

        meta = {
            "session_id": session_id,
            "role": role,
            "ts": str(int(time.time())),
        }
        if tags:
            meta["tags"] = ",".join(tags)
        if metadata:
            meta.update({k: str(v)[:200] for k, v in metadata.items()})

        if doc_id is None:
            doc_id = f"{session_id}-{int(time.time() * 1000)}"

        try:
            self._collection.add(documents=[text], ids=[doc_id], metadatas=[meta])
        except Exception as e:
            logger.warning(f"Semantic add failed: {e}")
            return ""
        return doc_id

    def search(self, query: str, n: int = 5,
               where: Optional[dict] = None) -> list[SemanticHit]:
        """语义搜索"""
        if not self.available or not query.strip():
            return []

        kwargs: dict = {"query_texts": [query], "n_results": min(max(n, 1), 50)}
        if where:
            kwargs["where"] = where

        try:
            res = self._collection.query(**kwargs)
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

        hits = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0] if res.get("distances") else [0.0] * len(docs)
        for i, doc in enumerate(docs):
            hits.append(SemanticHit(
                text=doc,
                metadata=metas[i] if i < len(metas) else {},
                distance=dists[i] if i < len(dists) else 0.0,
            ))
        return hits

    def count(self) -> int:
        if not self.available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def clear(self):
        """清空所有语义记忆（用于 reset）"""
        if not self.available or self._client is None:
            return
        try:
            from src.memory.embedder import build_embedder
            self._client.delete_collection(self.COLLECTION)
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION,
                embedding_function=build_embedder(),
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            logger.warning(f"Semantic clear failed: {e}")