-- evidence_research_v2.1.0 / shadow_demand_v2
-- Additive only. Does not DROP, ALTER, UPDATE, or DELETE
-- prediction_*, live_freeze_*, rolling_*, walkforward_*, signals_*,
-- platform_signals, runs, or director_v1 rows.
-- NULL stays NULL. New rows are append-only.

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_v2_adapter (
  adapter_id       TEXT PRIMARY KEY,
  platform         TEXT NOT NULL UNIQUE,
  cadence          TEXT NOT NULL,
  official_daily   INTEGER NOT NULL CHECK (official_daily IN (0,1)),
  availability     TEXT NOT NULL,
  reason           TEXT NOT NULL,
  version_id       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_v2_plan (
  plan_id               TEXT PRIMARY KEY,
  version_id            TEXT NOT NULL,
  formula_id            TEXT NOT NULL,
  as_of                 TEXT NOT NULL,
  window_start          TEXT NOT NULL,
  window_end_exclusive  TEXT NOT NULL,
  lookback_days         INTEGER NOT NULL,
  example_label         TEXT,
  review_commit         TEXT NOT NULL,
  created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_v2_plan_adapter (
  plan_id                  TEXT NOT NULL REFERENCES evidence_v2_plan(plan_id),
  adapter_id               TEXT NOT NULL REFERENCES evidence_v2_adapter(adapter_id),
  included_in_daily_score  INTEGER NOT NULL CHECK (included_in_daily_score IN (0,1)),
  reason                   TEXT NOT NULL,
  PRIMARY KEY (plan_id, adapter_id)
);

CREATE TABLE IF NOT EXISTS evidence_v2_observation (
  observation_id     TEXT PRIMARY KEY,
  plan_id            TEXT NOT NULL REFERENCES evidence_v2_plan(plan_id),
  identity_key       TEXT NOT NULL,
  revision           INTEGER NOT NULL,
  platform           TEXT NOT NULL,
  metric_key         TEXT NOT NULL,
  entity_kind        TEXT NOT NULL,
  entity_id          TEXT NOT NULL,
  shared_group_id    TEXT NOT NULL,
  value              REAL,
  unit               TEXT,
  status             TEXT NOT NULL,
  requested_cadence  TEXT NOT NULL,
  effective_cadence  TEXT NOT NULL,
  observed_start     TEXT,
  observed_end       TEXT,
  published_at       TEXT,
  collected_at       TEXT,
  available_at       TEXT,
  date_confidence    TEXT NOT NULL CHECK (date_confidence IN ('high','medium','unknown')),
  source_url         TEXT,
  source_note        TEXT NOT NULL,
  text_norm          TEXT,
  engagement_json    TEXT,
  is_partial         INTEGER NOT NULL CHECK (is_partial IN (0,1)),
  provenance_hash    TEXT NOT NULL,
  example_label      TEXT,
  inserted_at        TEXT NOT NULL,
  UNIQUE (identity_key, revision),
  UNIQUE (identity_key, provenance_hash)
);

CREATE INDEX IF NOT EXISTS idx_e2_obs_plan
  ON evidence_v2_observation(plan_id, identity_key);

CREATE TABLE IF NOT EXISTS evidence_v2_dedupe_link (
  link_id               TEXT PRIMARY KEY,
  plan_id               TEXT NOT NULL REFERENCES evidence_v2_plan(plan_id),
  left_observation_id   TEXT NOT NULL,
  right_observation_id  TEXT NOT NULL,
  method                TEXT NOT NULL,
  similarity            REAL,
  action                TEXT NOT NULL,
  note                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_v2_conflict (
  conflict_id             TEXT PRIMARY KEY,
  plan_id                 TEXT NOT NULL REFERENCES evidence_v2_plan(plan_id),
  identity_key            TEXT NOT NULL,
  earlier_observation_id  TEXT NOT NULL,
  later_observation_id    TEXT NOT NULL,
  reason                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_v2_v1_snapshot (
  plan_id      TEXT NOT NULL REFERENCES evidence_v2_plan(plan_id),
  entity_id    TEXT NOT NULL,
  v1_score     REAL,
  v1_rank      INTEGER,
  v1_formula   TEXT NOT NULL,
  note         TEXT NOT NULL,
  PRIMARY KEY (plan_id, entity_id)
);

CREATE TABLE IF NOT EXISTS evidence_v2_manifest (
  manifest_id            TEXT PRIMARY KEY,
  plan_id                TEXT NOT NULL REFERENCES evidence_v2_plan(plan_id),
  version_id             TEXT NOT NULL,
  formula_id             TEXT NOT NULL,
  as_of                  TEXT NOT NULL,
  replay_cutoff          TEXT NOT NULL,
  input_observation_ids  TEXT NOT NULL,
  input_hash             TEXT NOT NULL,
  status                 TEXT NOT NULL,
  disclaimer             TEXT NOT NULL,
  created_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_v2_shadow_score (
  manifest_id          TEXT NOT NULL REFERENCES evidence_v2_manifest(manifest_id),
  entity_id            TEXT NOT NULL,
  shared_group_id      TEXT NOT NULL,
  score                REAL,
  score_status         TEXT NOT NULL CHECK (score_status IN ('scored','pending')),
  pending_reason       TEXT,
  source_coverage      REAL NOT NULL,
  coverage_note        TEXT NOT NULL,
  uncertainty          TEXT NOT NULL,
  independent_group    INTEGER NOT NULL CHECK (independent_group IN (0,1)),
  n_skus_sharing       INTEGER NOT NULL,
  v1_score             REAL,
  v1_rank              INTEGER,
  v1_formula           TEXT,
  components_json      TEXT NOT NULL,
  PRIMARY KEY (manifest_id, entity_id),
  CHECK (
    (score_status = 'pending' AND score IS NULL)
    OR (score_status = 'scored' AND score IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS evidence_v2_shadow_compare (
  manifest_id                  TEXT PRIMARY KEY REFERENCES evidence_v2_manifest(manifest_id),
  n_entities                   INTEGER NOT NULL,
  n_scored                     INTEGER NOT NULL,
  n_pending                    INTEGER NOT NULL,
  n_independent_groups         INTEGER NOT NULL,
  n_scored_groups              INTEGER NOT NULL,
  descriptive_rank_agreement   REAL,
  note                         TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS evidence_v2_observation_no_update
BEFORE UPDATE ON evidence_v2_observation
BEGIN SELECT RAISE(ABORT, 'evidence_v2 observations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS evidence_v2_observation_no_delete
BEFORE DELETE ON evidence_v2_observation
BEGIN SELECT RAISE(ABORT, 'evidence_v2 observations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS evidence_v2_manifest_no_update
BEFORE UPDATE ON evidence_v2_manifest
BEGIN SELECT RAISE(ABORT, 'evidence_v2 manifests are append-only'); END;

CREATE TRIGGER IF NOT EXISTS evidence_v2_shadow_no_update
BEFORE UPDATE ON evidence_v2_shadow_score
BEGIN SELECT RAISE(ABORT, 'evidence_v2 shadow scores are append-only'); END;

CREATE TRIGGER IF NOT EXISTS evidence_v2_compare_no_update
BEFORE UPDATE ON evidence_v2_shadow_compare
BEGIN SELECT RAISE(ABORT, 'evidence_v2 comparisons are append-only'); END;

CREATE TRIGGER IF NOT EXISTS evidence_v2_v1_snapshot_no_update
BEFORE UPDATE ON evidence_v2_v1_snapshot
BEGIN SELECT RAISE(ABORT, 'evidence_v2 v1 snapshots are append-only'); END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('7');
