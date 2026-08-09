# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
import sqlite3
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.cards import CardRepo, CharacterCard
from src.tools.builtin.update_emotion import (
    update_emotion,
    MAX_DELTA_PERCENT,
    UpdateEmotionError,
)


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        r = CardRepo(db)
        with sqlite3.connect(db) as conn:
            r.ensure_tables(conn)
        cid = r.upsert_character(CharacterCard(
            id=None, name="X", description="d", personality="p",
            emotion_state={"affection": 50, "trust": 50, "mood": 0, "energy": 50,
                           "empathy": 50, "playfulness": 50, "formality": 50},
        ))
        yield r, cid


def test_update_emotion_applies_delta(repo):
    r, cid = repo
    result = update_emotion(r, cid, {"affection": 5}, "user shared story")
    assert result["updated"]["affection"] == 55
    assert len(result["audit_ids"]) > 0


def test_update_emotion_clamps_huge_delta(repo):
    r, cid = repo
    result = update_emotion(r, cid, {"affection": 999}, "test")
    assert result["updated"]["affection"] == 60


def test_update_emotion_clamps_negative_huge_delta(repo):
    r, cid = repo
    result = update_emotion(r, cid, {"affection": -999}, "test")
    assert result["updated"]["affection"] == 40


def test_update_emotion_rejects_empty_reason(repo):
    r, cid = repo
    with pytest.raises(UpdateEmotionError, match="reason"):
        update_emotion(r, cid, {"affection": 5}, "")


def test_update_emotion_rejects_unknown_metric(repo):
    r, cid = repo
    with pytest.raises(UpdateEmotionError, match="not in schema"):
        update_emotion(r, cid, {"unknown_thing": 5}, "test")


def test_update_emotion_writes_audit_row(repo):
    r, cid = repo
    update_emotion(r, cid, {"affection": 5}, "test reason", session_id="s1")
    with sqlite3.connect(r._db) as conn:
        rows = conn.execute(
            "SELECT character_id, metric_key, old_value, new_value, reason, session_id "
            "FROM emotion_audit WHERE character_id = ?", (cid,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "affection"
    assert rows[0][2] == 50
    assert rows[0][3] == 55
    assert rows[0][4] == "test reason"
    assert rows[0][5] == "s1"


def test_max_delta_percent_constant():
    import src.tools.builtin.update_emotion as mod
    assert mod.MAX_DELTA_PERCENT == 0.1


def test_tool_falls_back_to_first_character_when_no_default(repo, monkeypatch):
    import asyncio
    import json

    import src.tools.builtin.update_emotion as mod

    r, cid = repo
    monkeypatch.setattr(mod, "_resolve_repo_path", lambda: Path(r._db))

    tool = mod.UpdateEmotionTool()
    out = asyncio.run(tool.execute(deltas={"mood": 2}, reason="warm greeting"))

    assert "[ERROR]" not in out
    assert json.loads(out)["updated"]["mood"] == 2
