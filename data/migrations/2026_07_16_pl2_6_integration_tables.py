"""Create PL2.6 integration and token accounting tables."""

from __future__ import annotations

import sqlite3

NAME = "2026_07_16_pl2_6_integration_tables"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  base_url TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL,
  persona_prompt TEXT NOT NULL,
  specialty TEXT DEFAULT '',
  temperature REAL DEFAULT 0.7,
  max_tokens INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS integrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT DEFAULT '',
  main_model_id INTEGER NOT NULL,
  rounds INTEGER NOT NULL DEFAULT 2 CHECK(rounds BETWEEN 1 AND 5),
  max_depth INTEGER NOT NULL DEFAULT 2 CHECK(max_depth BETWEEN 1 AND 8),
  max_subs_picked INTEGER DEFAULT 2,
  is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(main_model_id) REFERENCES models(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS integration_subs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  integration_id INTEGER NOT NULL,
  position INTEGER NOT NULL,
  display_name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('model','integration')),
  model_id INTEGER,
  child_integration_id INTEGER,
  FOREIGN KEY(integration_id) REFERENCES integrations(id) ON DELETE CASCADE,
  FOREIGN KEY(model_id) REFERENCES models(id) ON DELETE RESTRICT,
  FOREIGN KEY(child_integration_id) REFERENCES integrations(id) ON DELETE CASCADE,
  UNIQUE(integration_id, position)
);

CREATE INDEX IF NOT EXISTS idx_subs_child ON integration_subs(child_integration_id)
  WHERE child_integration_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS integration_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  integration_id INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  user_message TEXT,
  final_reply TEXT,
  total_calls INTEGER NOT NULL DEFAULT 0,
  total_cost_usd REAL,
  status TEXT,
  FOREIGN KEY(integration_id) REFERENCES integrations(id)
);

CREATE TABLE IF NOT EXISTS llm_token_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  integration_run_id INTEGER,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cost_usd REAL,
  FOREIGN KEY(integration_run_id) REFERENCES integration_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON llm_token_usage(ts);
CREATE INDEX IF NOT EXISTS idx_token_usage_run ON llm_token_usage(integration_run_id);
"""

DROP_SQL = """
DROP TABLE IF EXISTS llm_token_usage;
DROP TABLE IF EXISTS integration_runs;
DROP TABLE IF EXISTS integration_subs;
DROP TABLE IF EXISTS integrations;
DROP TABLE IF EXISTS models;
"""


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(CREATE_SQL)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(models)").fetchall()}
    if "base_url" not in columns:
        conn.execute("ALTER TABLE models ADD COLUMN base_url TEXT NOT NULL DEFAULT ''")
    if "api_key" not in columns:
        conn.execute("ALTER TABLE models ADD COLUMN api_key TEXT NOT NULL DEFAULT ''")
    if "protocol" not in columns:
        conn.execute("ALTER TABLE models ADD COLUMN protocol TEXT NOT NULL DEFAULT ''")
    conn.commit()


def down(conn: sqlite3.Connection) -> None:
    conn.executescript(DROP_SQL)
    conn.commit()
