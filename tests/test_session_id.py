"""Tests for src/utils/session_id.py — persistent process-level session id."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import session_id


def test_first_call_generates_and_persists():
    session_id.reset_session_id_cache()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "data" / "llm_cache.db"
        sid = session_id.get_or_create_session_id(cache_db_path=path)
        assert isinstance(sid, str) and len(sid) >= 16
        persisted = (Path(d) / "data" / ".llm_session_id").read_text().strip()
        assert persisted == sid


def test_subsequent_calls_return_same():
    session_id.reset_session_id_cache()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "data" / "llm_cache.db"
        first = session_id.get_or_create_session_id(cache_db_path=path)
        second = session_id.get_or_create_session_id(cache_db_path=path)
        assert first == second


def test_env_override_takes_precedence():
    session_id.reset_session_id_cache()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "data" / "llm_cache.db"
        os.environ["LLM_CACHE_SESSION_ID"] = "env-sid"
        try:
            sid = session_id.get_or_create_session_id(cache_db_path=path)
            assert sid == "env-sid"
        finally:
            del os.environ["LLM_CACHE_SESSION_ID"]
            session_id.reset_session_id_cache()


def test_arg_override_takes_precedence():
    session_id.reset_session_id_cache()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "data" / "llm_cache.db"
        sid = session_id.get_or_create_session_id(cache_db_path=path, override="arg-sid")
        assert sid == "arg-sid"


def test_survives_restart_via_disk():
    session_id.reset_session_id_cache()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "data" / "llm_cache.db"
        first = session_id.get_or_create_session_id(cache_db_path=path)
        session_id.reset_session_id_cache()
        again = session_id.get_or_create_session_id(cache_db_path=path)
        assert first == again