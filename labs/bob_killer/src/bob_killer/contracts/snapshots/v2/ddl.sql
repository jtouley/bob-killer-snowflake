CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed')),
  created_at TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  PRIMARY KEY (run_id)
) STRICT;

CREATE TABLE IF NOT EXISTS stage_status (
  run_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pending', 'running', 'succeeded', 'failed', 'skipped')),
  detail TEXT NOT NULL,
  PRIMARY KEY (run_id, stage)
) STRICT;
