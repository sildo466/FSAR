"""Process-level session_id, persisted across restarts.

The Responses API uses `prompt_cache_key` to route requests to a server-side
prefix cache. The key needs to be stable across calls within a session — but
also stable across restarts, otherwise every restart wipes the server-side
cache and defeats the purpose.

This module generates a UUID on first call and persists it to
`data/.llm_session_id`. Subsequent reads return the same value. The caller
can override via env `LLM_CACHE_SESSION_ID` or the `llm.cache.session_id`
settings field.
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

_SESSION_FILE_NAME = ".llm_session_id"
_SESSION_LOCK = threading.Lock()
_RESOLVED: str | None = None


def _resolve_path(db_path: str | Path) -> Path:
    p = Path(db_path)
    parent = p if p.is_dir() or p.suffix == "" else p.parent
    return parent / _SESSION_FILE_NAME


def _read_from_disk(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None


def _write_to_disk(path: Path, value: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(value, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


def get_or_create_session_id(
    *,
    cache_db_path: str | Path = "data/llm_cache.db",
    override: str | None = None,
) -> str:
    """Return the persistent session_id for this fsar install.

    Resolution order:
      1. `override` argument (if provided)
      2. `LLM_CACHE_SESSION_ID` environment variable
      3. The contents of `<cache_db_dir>/.llm_session_id`
      4. Generate a new UUID4 and persist it
    """
    global _RESOLVED
    if _RESOLVED is not None:
        return _RESOLVED

    with _SESSION_LOCK:
        if _RESOLVED is not None:
            return _RESOLVED

        if override and override.strip():
            _RESOLVED = override.strip()
            return _RESOLVED

        env_val = os.environ.get("LLM_CACHE_SESSION_ID", "").strip()
        if env_val:
            _RESOLVED = env_val
            return _RESOLVED

        path = _resolve_path(cache_db_path)
        existing = _read_from_disk(path)
        if existing:
            _RESOLVED = existing
            return _RESOLVED

        new_id = str(uuid.uuid4())
        _write_to_disk(path, new_id)
        _RESOLVED = new_id
        return _RESOLVED


def reset_session_id_cache() -> None:
    """Test hook — forget the in-process resolution so the next call re-reads
    from disk (or regenerates)."""
    global _RESOLVED
    with _SESSION_LOCK:
        _RESOLVED = None