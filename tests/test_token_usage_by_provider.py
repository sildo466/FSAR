# SPDX-License-Identifier: MIT
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.memory.integrations import get_token_usage_by_provider


def test_get_token_usage_by_provider_aggregates(tmp_path: Path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE llm_token_usage ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,"
        "integration_run_id INTEGER, provider TEXT NOT NULL, model TEXT NOT NULL,"
        "input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cost_usd REAL)"
    )
    conn.executemany(
        "INSERT INTO llm_token_usage(ts,provider,model,input_tokens,output_tokens,cost_usd)"
        " VALUES(?,?,?,?,?,?)",
        [
            ("2026-08-01T10:00:00", "p1", "model-a", 100, 10, 0.01),
            ("2026-08-02T10:00:00", "p1", "model-a", 200, 20, 0.02),
            ("2026-08-03T10:00:00", "p2", "model-b", 50, 5, 0.005),
            ("2026-08-04T10:00:00", "p2", "model-b", 0, 0, None),
            ("2026-08-05T10:00:00", "p1", "model-c", 9999, 9999, 0),
        ],
    )
    conn.commit()
    conn.close()

    out = get_token_usage_by_provider(db_path=db, from_ts="2026-08-01", to_ts="2026-08-31")
    by = {r["provider"]: r for r in out}
    assert by["p1"]["prompt_tokens"] == 100 + 200 + 9999
    assert by["p1"]["completion_tokens"] == 10 + 20 + 9999
    assert by["p1"]["model"] == "model-c"
    assert by["p1"]["cost_usd"] == 0.03
    assert by["p2"]["prompt_tokens"] == 50
    assert by["p2"]["completion_tokens"] == 5
    assert len(out) == 2


def test_get_token_usage_by_provider_respects_date_range(tmp_path: Path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE llm_token_usage ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,"
        "integration_run_id INTEGER, provider TEXT NOT NULL, model TEXT NOT NULL,"
        "input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cost_usd REAL)"
    )
    conn.executemany(
        "INSERT INTO llm_token_usage(ts,provider,model,input_tokens,output_tokens,cost_usd)"
        " VALUES(?,?,?,?,?,?)",
        [
            ("2026-08-01T10:00:00", "p1", "m", 100, 10, None),
            ("2026-08-11T10:00:00", "p1", "m", 50, 5, None),
        ],
    )
    conn.commit()
    conn.close()

    out = get_token_usage_by_provider(db_path=db, from_ts="2026-08-10", to_ts="2026-08-12")
    assert len(out) == 1
    assert out[0]["prompt_tokens"] == 50
