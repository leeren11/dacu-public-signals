-- youtube_official_feed_v1. Additive shadow storage.
-- Does not ALTER prediction_*, live_freeze_*, rolling_*, walkforward_*,
-- signals_*, platform_signals, or evidence_v2_* score tables.

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS youtube_feed_policy (
  policy_id            TEXT PRIMARY KEY,
  retention_days       INTEGER NOT NULL CHECK (retention_days BETWEEN 1 AND 30),
  license_basis        TEXT NOT NULL,
  delta_disclosure     TEXT NOT NULL,
  statistics_are_score INTEGER NOT NULL DEFAULT 0 CHECK (statistics_are_score = 0)
);

CREATE TABLE IF NOT EXISTS youtube_feed_watchlist (
  source              TEXT NOT NULL,
  channel_id          TEXT NOT NULL,
  watchlist_version   TEXT NOT NULL,
  handle              TEXT NOT NULL,
  scope               TEXT NOT NULL,
  business_role       TEXT NOT NULL,
  maps_to_sku         INTEGER NOT NULL CHECK (maps_to_sku = 0),
  provenance_url      TEXT,
  approved_at         TEXT,
  included_from       TEXT NOT NULL,
  status              TEXT NOT NULL,
  example_label       TEXT NOT NULL,
  PRIMARY KEY (source, channel_id, watchlist_version)
);

CREATE TABLE IF NOT EXISTS youtube_feed_evidence (
  evidence_id          TEXT PRIMARY KEY,
  source               TEXT NOT NULL,
  channel_id           TEXT NOT NULL,
  request_url          TEXT NOT NULL,
  retrieved_at         TEXT NOT NULL,
  first_available_at   TEXT NOT NULL,
  http_status          INTEGER,
  content_type         TEXT,
  response_path        TEXT,
  response_sha256      TEXT,
  response_bytes       INTEGER,
  saved_bytes          INTEGER,
  truncated            INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
  status               TEXT NOT NULL,
  missing_reason       TEXT,
  license_basis        TEXT NOT NULL,
  watchlist_version    TEXT NOT NULL,
  etag                 TEXT,
  not_modified_of      TEXT,
  example_label        TEXT,
  UNIQUE (source, request_url, retrieved_at, response_sha256)
);

CREATE TABLE IF NOT EXISTS youtube_feed_snapshot (
  evidence_id            TEXT NOT NULL REFERENCES youtube_feed_evidence(evidence_id),
  source_object_id       TEXT NOT NULL,
  channel_id             TEXT NOT NULL,
  published_at           TEXT,
  feed_updated_at        TEXT,
  retrieved_at           TEXT NOT NULL,
  metric_key             TEXT NOT NULL,
  value                  REAL,
  unit                   TEXT NOT NULL,
  source_url             TEXT NOT NULL,
  title                  TEXT,
  content_tag            TEXT,
  category_rule_version  TEXT,
  is_proxy               INTEGER NOT NULL DEFAULT 1 CHECK (is_proxy = 1),
  maps_to_sku            INTEGER NOT NULL DEFAULT 0 CHECK (maps_to_sku = 0),
  not_for_scoring        INTEGER NOT NULL DEFAULT 1 CHECK (not_for_scoring = 1),
  status                 TEXT NOT NULL,
  missing_reason         TEXT,
  PRIMARY KEY (evidence_id, source_object_id, metric_key),
  CHECK (status <> 'observed' OR value IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS youtube_feed_object_seen (
  source_object_id    TEXT PRIMARY KEY,
  first_available_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS youtube_feed_cohort_delta (
  earlier_evidence_id TEXT NOT NULL,
  later_evidence_id   TEXT NOT NULL,
  source_object_id    TEXT NOT NULL,
  earlier_value       REAL,
  later_value         REAL,
  delta_value         REAL,
  hours_between       REAL,
  status              TEXT NOT NULL,
  missing_reason      TEXT,
  disclosure          TEXT NOT NULL,
  not_for_scoring     INTEGER NOT NULL DEFAULT 1 CHECK (not_for_scoring = 1),
  PRIMARY KEY (earlier_evidence_id, later_evidence_id, source_object_id)
);

CREATE TABLE IF NOT EXISTS youtube_feed_source_state (
  channel_id   TEXT PRIMARY KEY,
  state        TEXT NOT NULL,
  http_status  INTEGER,
  reason       TEXT NOT NULL,
  stopped_at   TEXT,
  retry_after  TEXT
);

CREATE TABLE IF NOT EXISTS youtube_feed_disabled_source (
  source_id  TEXT PRIMARY KEY,
  state      TEXT NOT NULL,
  reason     TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('8');
