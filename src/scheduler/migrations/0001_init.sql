CREATE TABLE IF NOT EXISTS scheduled_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  description TEXT DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,

  schedule_kind TEXT NOT NULL CHECK(schedule_kind IN ('cron','interval','at','startup')),
  schedule_expr TEXT NOT NULL,
  timezone TEXT DEFAULT '',

  job_kind TEXT NOT NULL CHECK(job_kind IN ('system','agent')),
  prompt TEXT NOT NULL DEFAULT '',
  tools_allow TEXT DEFAULT '',
  model_override TEXT DEFAULT '',
  timeout_seconds INTEGER NOT NULL DEFAULT 60,

  delivery_mode TEXT NOT NULL CHECK(delivery_mode IN ('db_only','social')),
  delivery_target TEXT DEFAULT '',

  running_at TEXT,
  last_run_at TEXT,
  last_status TEXT,
  last_error TEXT DEFAULT '',
  consecutive_errors INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_enabled ON scheduled_jobs(enabled);

CREATE TABLE IF NOT EXISTS job_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
  expected_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  duration_ms INTEGER,
  status TEXT NOT NULL CHECK(status IN ('ok','error','skipped','missed','running')),
  error TEXT DEFAULT '',
  error_class TEXT DEFAULT '',
  result_text TEXT DEFAULT '',
  delivery_status TEXT DEFAULT '',
  delivery_error TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_job ON job_runs(job_id, created_at DESC);
