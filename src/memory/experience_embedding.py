"""Phase 6.7 — on-demand ChromaDB-backed vector search for experiences + memory chunks.

Embedding is lazy: rows are embedded the first time they're loaded via
experience_view (or memory search). Avoids cold-start cost + stale index.

Storage:
    data/chroma/experiences/<name>.json     ← id + vector + tiny metadata
    data/chroma/memory_chunks/<id>.json     ← same shape

Search: cosine similarity. Falls back to SQL LIKE when no vectors exist.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from src.utils.config import get_config
from src.utils.fsar_home import get_fsar_home
from src.utils.logger import logger


_singleton = None


def get_embedder():
    """Lazy singleton — built once, reused across the session."""
    global _singleton
    if _singleton is None:
        from src.memory.embedder import build_embedder
        try:
            _singleton = build_embedder()
        except Exception as e:
            logger.warning(
                f"embedder init failed: {e} — semantic recall will be disabled. "
                "Configure memory.embedder.* in Settings → Embedding."
            )
            return None
    return _singleton


def _chroma_root() -> Path:
    default = str(get_fsar_home() / "data" / "chroma")
    return Path(get_config().get("memory.chroma_path", default))


def _vec_path(table: str, key: str) -> Path:
    p = _chroma_root() / table
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def ensure_embedded(embedder: Any, row_id: int, text: str,
                    *, table: str = "experiences") -> None:
    """Embed row text on first view. Persists the vector to disk.

    Embedders may be slow — failures are logged at DEBUG and skipped silently.
    Supports both single-text and list-text embedder APIs.
    """
    if not text.strip():
        return
    path = _vec_path(table, str(row_id))
    if path.exists():
        return
    snippet = text[:2000]
    try:
        out = embedder.embed([snippet])
        vec = list(out[0]) if out else []
    except TypeError:
        try:
            vec = list(embedder.embed(snippet))
        except Exception as e:
            logger.debug(f"embed (single) failed for {table}#{row_id}: {e}")
            return
    except Exception as e:
        logger.debug(f"embed failed for {table}#{row_id}: {e}")
        return
    if not vec:
        return
    path.write_text(
        json.dumps({"id": row_id, "text": snippet[:200], "vector": vec}),
        encoding="utf-8",
    )
    logger.debug(f"embedded {table}#{row_id} dim={len(vec)}")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _load_all_vectors(table: str) -> list[dict]:
    root = _chroma_root() / table
    if not root.exists():
        return []
    out: list[dict] = []
    for p in root.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data.get("vector"), list):
                out.append(data)
        except Exception:
            continue
    return out


def search(query_vec: list[float], *, table: str,
           limit: int = 5) -> list[dict]:
    """Return top-k rows by cosine similarity, sorted descending.

    Each result = {id, text, score}.
    """
    if not query_vec:
        return []
    rows = _load_all_vectors(table)
    if not rows:
        return []
    scored = [(cosine(query_vec, r["vector"]), r) for r in rows]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"id": r["id"], "text": r["text"], "score": float(s)}
        for s, r in scored[:limit] if s > 0
    ]


def best_match(query: str, embedder: Any, *, table: str = "experiences",
               limit: int = 1) -> list[dict]:
    """Embed the query, return top-k. Returns [] when embedder is None."""
    if embedder is None or not query.strip():
        return []
    try:
        out = embedder.embed([query[:2000]])
        qv = list(out[0]) if out else []
    except TypeError:
        try:
            qv = list(embedder.embed(query[:2000]))
        except Exception:
            return []
    except Exception:
        return []
    return search(qv, table=table, limit=limit)
