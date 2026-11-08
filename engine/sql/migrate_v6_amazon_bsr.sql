-- dacu-signal Amazon BSR evidence layer (amazon_bsr_v1)
-- Additive only. Does not DROP, ALTER, UPDATE, or DELETE any pre-existing table.
-- Does not read or write prediction_*, live_freeze_*, rolling_*, walkforward_*, or signals_*.
-- Target-group seed rows are inserted by scripts/amazon_bsr/db.py (no ASIN samples).
-- Apply with: python3 scripts/amazon_bsr_cli.py migrate --db <path>
-- PRAGMA foreign_keys is set by that CLI before this script starts.

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS amazon_source (
  source_id    TEXT PRIMARY KEY,
  source_name  TEXT NOT NULL,
  docs_url     TEXT NOT NULL,
  license_note TEXT NOT NULL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS amazon_layer_note (
  note_id    TEXT PRIMARY KEY,
  note       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS amazon_target_group (
  sku_cluster            TEXT PRIMARY KEY,
  domain_id              INTEGER NOT NULL CHECK (domain_id = 1),
  display_zh             TEXT NOT NULL,
  attribute_policy_json  TEXT NOT NULL,
  recommended_pool_min   INTEGER NOT NULL CHECK (recommended_pool_min >= 0),
  recommended_pool_max   INTEGER NOT NULL CHECK (recommended_pool_max >= recommended_pool_min),
  pool_status            TEXT NOT NULL CHECK (pool_status IN (
                           'needs_input','below_recommended','within_recommended','above_recommended')),
  pool_count             INTEGER NOT NULL CHECK (pool_count >= 0),
  notes                  TEXT NOT NULL,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at             TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS amazon_target_group_no_delete
BEFORE DELETE ON amazon_target_group
BEGIN
  SELECT RAISE(ABORT, 'amazon_target_group cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS amazon_target_group_no_definition_update
BEFORE UPDATE OF sku_cluster, domain_id, display_zh, attribute_policy_json,
  recommended_pool_min, recommended_pool_max, notes, created_at
ON amazon_target_group
BEGIN
  SELECT RAISE(ABORT, 'amazon_target_group definition is immutable; pool_status and pool_count may change');
END;

CREATE TABLE IF NOT EXISTS amazon_mapping_version (
  mapping_version  TEXT PRIMARY KEY,
  domain_id        INTEGER NOT NULL CHECK (domain_id = 1),
  valid_from       TEXT NOT NULL,
  provenance_json  TEXT NOT NULL,
  content_hash     TEXT NOT NULL,
  recorded_at      TEXT NOT NULL,
  item_count       INTEGER NOT NULL,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS amazon_mapping_version_no_update
BEFORE UPDATE ON amazon_mapping_version
BEGIN
  SELECT RAISE(ABORT, 'amazon_mapping_version is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_mapping_version_no_delete
BEFORE DELETE ON amazon_mapping_version
BEGIN
  SELECT RAISE(ABORT, 'amazon_mapping_version is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_asin_map (
  map_id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  mapping_version            TEXT NOT NULL REFERENCES amazon_mapping_version(mapping_version) ON DELETE RESTRICT,
  sku_cluster                TEXT NOT NULL REFERENCES amazon_target_group(sku_cluster) ON DELETE RESTRICT,
  asin                       TEXT NOT NULL,
  domain_id                  INTEGER NOT NULL CHECK (domain_id = 1),
  role                       TEXT NOT NULL CHECK (role IN ('parent','child','standalone')),
  parent_asin                TEXT,
  variation_attributes_json  TEXT NOT NULL,
  product_attributes_json    TEXT NOT NULL,
  category_ids_json          TEXT NOT NULL,
  inclusion_reason           TEXT NOT NULL,
  inclusion_facet            TEXT,
  provenance_json            TEXT NOT NULL,
  valid_from                 TEXT NOT NULL,
  valid_to                   TEXT,
  is_current                 INTEGER NOT NULL CHECK (is_current IN (0,1)),
  recorded_at                TEXT NOT NULL,
  content_hash               TEXT NOT NULL,
  created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (mapping_version, sku_cluster, asin, domain_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_amazon_asin_map_one_current
  ON amazon_asin_map(asin, domain_id)
  WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS idx_amazon_asin_map_lookup
  ON amazon_asin_map(asin, domain_id, recorded_at);

CREATE TRIGGER IF NOT EXISTS amazon_asin_map_no_delete
BEFORE DELETE ON amazon_asin_map
BEGIN
  SELECT RAISE(ABORT, 'amazon_asin_map is append-only; set valid_to to retire');
END;

CREATE TRIGGER IF NOT EXISTS amazon_asin_map_no_evidence_update
BEFORE UPDATE OF
  mapping_version, sku_cluster, asin, domain_id, role, parent_asin,
  variation_attributes_json, product_attributes_json, category_ids_json,
  inclusion_reason, inclusion_facet, provenance_json, valid_from,
  recorded_at, content_hash, map_id
ON amazon_asin_map
BEGIN
  SELECT RAISE(ABORT, 'amazon_asin_map evidence is append-only; close the row and insert a new version');
END;

CREATE TABLE IF NOT EXISTS amazon_ingest_batch (
  batch_id                  TEXT PRIMARY KEY,
  source_id                 TEXT NOT NULL REFERENCES amazon_source(source_id) ON DELETE RESTRICT,
  source_kind               TEXT NOT NULL CHECK (source_kind IN ('offline_file','live_api')),
  domain_id                 INTEGER NOT NULL CHECK (domain_id = 1),
  started_at                TEXT NOT NULL,
  finished_at               TEXT,
  status                    TEXT NOT NULL,
  status_reason             TEXT,
  request_params_json       TEXT NOT NULL,
  sanitized                 INTEGER NOT NULL CHECK (sanitized = 1),
  token_budget              INTEGER,
  tokens_consumed_reported  INTEGER,
  tokens_left_reported      INTEGER,
  refill_in_reported        INTEGER,
  refill_rate_reported      INTEGER,
  known_since               TEXT,
  known_since_reason        TEXT,
  retrieved_at              TEXT,
  source_response_at        TEXT,
  license_note              TEXT NOT NULL,
  file_name                 TEXT,
  file_sha256               TEXT,
  item_count                INTEGER NOT NULL DEFAULT 0,
  inserted_observations     INTEGER NOT NULL DEFAULT 0,
  duplicate_observations    INTEGER NOT NULL DEFAULT 0,
  revision_observations     INTEGER NOT NULL DEFAULT 0,
  secrets_redacted          INTEGER NOT NULL DEFAULT 0,
  created_at                TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS amazon_ingest_batch_no_delete
BEFORE DELETE ON amazon_ingest_batch
BEGIN
  SELECT RAISE(ABORT, 'amazon_ingest_batch cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS amazon_ingest_batch_no_evidence_update
BEFORE UPDATE OF
  batch_id, source_id, source_kind, domain_id, started_at, request_params_json,
  sanitized, known_since, known_since_reason, license_note, file_name, file_sha256
ON amazon_ingest_batch
BEGIN
  SELECT RAISE(ABORT, 'amazon_ingest_batch request evidence is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_request (
  request_id             TEXT PRIMARY KEY,
  batch_id               TEXT NOT NULL REFERENCES amazon_ingest_batch(batch_id) ON DELETE RESTRICT,
  requested_at           TEXT NOT NULL,
  endpoint               TEXT NOT NULL,
  sanitized_params_json  TEXT NOT NULL,
  http_status            INTEGER,
  tokens_consumed        INTEGER,
  tokens_left            INTEGER,
  refill_in              INTEGER,
  refill_rate            INTEGER,
  error_redacted         TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS amazon_request_no_update
BEFORE UPDATE ON amazon_request
BEGIN
  SELECT RAISE(ABORT, 'amazon_request is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_request_no_delete
BEFORE DELETE ON amazon_request
BEGIN
  SELECT RAISE(ABORT, 'amazon_request is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_raw_payload (
  raw_id                     TEXT PRIMARY KEY,
  batch_id                   TEXT NOT NULL REFERENCES amazon_ingest_batch(batch_id) ON DELETE RESTRICT,
  payload_role               TEXT NOT NULL CHECK (payload_role IN ('file','product','response_envelope')),
  asin                       TEXT,
  domain_id                  INTEGER,
  content_hash               TEXT NOT NULL,
  payload_encoding           TEXT NOT NULL CHECK (payload_encoding IN ('utf8_json','gzip_json')),
  payload_blob               BLOB NOT NULL,
  blob_sha256                TEXT NOT NULL,
  uncompressed_bytes         INTEGER NOT NULL,
  secrets_redacted           INTEGER NOT NULL DEFAULT 0,
  retrieved_at               TEXT NOT NULL,
  first_available_to_system  TEXT NOT NULL,
  license_note               TEXT NOT NULL,
  created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (payload_role, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_amazon_raw_asin
  ON amazon_raw_payload(asin, domain_id);

CREATE TRIGGER IF NOT EXISTS amazon_raw_no_update
BEFORE UPDATE ON amazon_raw_payload
BEGIN
  SELECT RAISE(ABORT, 'amazon_raw_payload is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_raw_no_delete
BEFORE DELETE ON amazon_raw_payload
BEGIN
  SELECT RAISE(ABORT, 'amazon_raw_payload is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_product_snapshot (
  snapshot_id                INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_id                     TEXT NOT NULL UNIQUE REFERENCES amazon_raw_payload(raw_id) ON DELETE RESTRICT,
  asin                       TEXT NOT NULL,
  domain_id                  INTEGER NOT NULL CHECK (domain_id = 1),
  product_type               INTEGER,
  title                      TEXT,
  brand                      TEXT,
  color                      TEXT,
  size                       TEXT,
  material                   TEXT,
  parent_asin                TEXT,
  root_category_id           TEXT,
  category_ids_json          TEXT NOT NULL,
  attributes_json            TEXT NOT NULL,
  decode_notes_json          TEXT NOT NULL,
  listed_since_raw           INTEGER,
  listed_since_at            TEXT,
  tracking_since_at          TEXT,
  last_update_at             TEXT,
  last_rating_update_at      TEXT,
  last_stock_update_at       TEXT,
  availability_amazon        INTEGER,
  observed_at                TEXT,
  retrieved_at               TEXT NOT NULL,
  first_available_to_system  TEXT NOT NULL,
  created_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS amazon_snapshot_no_update
BEFORE UPDATE ON amazon_product_snapshot
BEGIN
  SELECT RAISE(ABORT, 'amazon_product_snapshot is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_snapshot_no_delete
BEFORE DELETE ON amazon_product_snapshot
BEGIN
  SELECT RAISE(ABORT, 'amazon_product_snapshot is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_variation_seen (
  id                         INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_id                     TEXT NOT NULL REFERENCES amazon_raw_payload(raw_id) ON DELETE RESTRICT,
  domain_id                  INTEGER NOT NULL CHECK (domain_id = 1),
  parent_asin                TEXT NOT NULL,
  child_asin                 TEXT NOT NULL,
  attributes_json            TEXT NOT NULL,
  image_filename             TEXT,
  variation_scope            TEXT NOT NULL CHECK (variation_scope IN ('live_variation','historical_or_oos')),
  observed_at                TEXT,
  retrieved_at               TEXT NOT NULL,
  first_available_to_system  TEXT NOT NULL,
  natural_key                TEXT NOT NULL UNIQUE,
  created_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS amazon_variation_no_update
BEFORE UPDATE ON amazon_variation_seen
BEGIN
  SELECT RAISE(ABORT, 'amazon_variation_seen is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_variation_no_delete
BEFORE DELETE ON amazon_variation_seen
BEGIN
  SELECT RAISE(ABORT, 'amazon_variation_seen is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_series_presence (
  raw_id        TEXT NOT NULL REFERENCES amazon_raw_payload(raw_id) ON DELETE RESTRICT,
  source_field  TEXT NOT NULL,
  present       INTEGER NOT NULL CHECK (present IN (0,1)),
  point_count   INTEGER,
  note          TEXT NOT NULL,
  PRIMARY KEY (raw_id, source_field)
);

CREATE TRIGGER IF NOT EXISTS amazon_presence_no_update
BEFORE UPDATE ON amazon_series_presence
BEGIN
  SELECT RAISE(ABORT, 'amazon_series_presence is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_presence_no_delete
BEFORE DELETE ON amazon_series_presence
BEGIN
  SELECT RAISE(ABORT, 'amazon_series_presence is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_category_name (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_id    INTEGER NOT NULL CHECK (domain_id = 1),
  category_id  TEXT NOT NULL,
  name         TEXT NOT NULL,
  raw_id       TEXT NOT NULL REFERENCES amazon_raw_payload(raw_id) ON DELETE RESTRICT,
  recorded_at  TEXT NOT NULL,
  UNIQUE (domain_id, category_id, name, raw_id)
);

CREATE TRIGGER IF NOT EXISTS amazon_category_name_no_update
BEFORE UPDATE ON amazon_category_name
BEGIN
  SELECT RAISE(ABORT, 'amazon_category_name is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_category_name_no_delete
BEFORE DELETE ON amazon_category_name
BEGIN
  SELECT RAISE(ABORT, 'amazon_category_name is immutable');
END;

CREATE TABLE IF NOT EXISTS amazon_observation (
  observation_id             INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_id                     TEXT NOT NULL REFERENCES amazon_raw_payload(raw_id) ON DELETE RESTRICT,
  batch_id                   TEXT NOT NULL REFERENCES amazon_ingest_batch(batch_id) ON DELETE RESTRICT,
  asin                       TEXT NOT NULL,
  domain_id                  INTEGER NOT NULL CHECK (domain_id = 1),
  series_kind                TEXT NOT NULL,
  category_id                TEXT,
  category_name              TEXT,
  category_resolution        TEXT NOT NULL,
  observed_at                TEXT NOT NULL,
  keepa_time_minutes         INTEGER,
  retrieved_at               TEXT NOT NULL,
  first_available_to_system  TEXT NOT NULL,
  value_num                  REAL,
  value_text                 TEXT,
  value_missing_reason       TEXT,
  sentinel_raw               INTEGER,
  currency                   TEXT,
  price_type                 TEXT,
  price_cents                INTEGER,
  shipping_cents             INTEGER,
  price_basis                TEXT,
  count_kind                 TEXT,
  count_scope                TEXT,
  definition_variant         TEXT NOT NULL CHECK (length(definition_variant) > 0),
  source_field               TEXT NOT NULL,
  source_updated_at          TEXT,
  source_update_status       TEXT NOT NULL,
  source_update_reason       TEXT NOT NULL,
  stock_qty                  INTEGER,
  offer_id                   TEXT,
  seller_id                  TEXT,
  offer_condition            INTEGER,
  is_valid_measurement       INTEGER NOT NULL CHECK (is_valid_measurement IN (0,1)),
  revision_seq               INTEGER NOT NULL CHECK (revision_seq >= 1),
  supersedes_observation_id  INTEGER,
  revision_reason            TEXT,
  natural_key                TEXT NOT NULL UNIQUE,
  conflict_key               TEXT NOT NULL,
  created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (is_valid_measurement = 0 OR value_num IS NOT NULL),
  CHECK (is_valid_measurement = 0 OR series_kind NOT IN ('bsr_sales_ranks','bsr_csv_sales') OR value_num > 0)
);

CREATE INDEX IF NOT EXISTS idx_amazon_obs_series
  ON amazon_observation(asin, domain_id, series_kind, category_id, definition_variant, observed_at);

CREATE INDEX IF NOT EXISTS idx_amazon_obs_conflict
  ON amazon_observation(conflict_key, revision_seq);

CREATE INDEX IF NOT EXISTS idx_amazon_obs_known
  ON amazon_observation(first_available_to_system, observed_at);

CREATE TRIGGER IF NOT EXISTS amazon_observation_no_update
BEFORE UPDATE ON amazon_observation
BEGIN
  SELECT RAISE(ABORT, 'amazon_observation is append-only; insert a revision');
END;

CREATE TRIGGER IF NOT EXISTS amazon_observation_no_delete
BEFORE DELETE ON amazon_observation
BEGIN
  SELECT RAISE(ABORT, 'amazon_observation is append-only');
END;

CREATE TABLE IF NOT EXISTS amazon_derived_metric (
  metric_id              INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_version         TEXT NOT NULL,
  policy_id              TEXT NOT NULL,
  asin                   TEXT NOT NULL,
  domain_id              INTEGER NOT NULL CHECK (domain_id = 1),
  series_kind            TEXT NOT NULL,
  category_id            TEXT,
  category_key           TEXT NOT NULL,
  definition_variant     TEXT NOT NULL,
  count_kind             TEXT,
  as_of_utc_date         TEXT NOT NULL,
  selection_cutoff       TEXT NOT NULL,
  start_observation_id   INTEGER,
  end_observation_id     INTEGER,
  start_observed_at      TEXT,
  end_observed_at        TEXT,
  start_first_available  TEXT,
  end_first_available    TEXT,
  span_days              REAL,
  raw_point_count        INTEGER,
  daily_snapshot_count   INTEGER,
  value                  REAL,
  unit                   TEXT NOT NULL,
  interpretation         TEXT NOT NULL,
  status                 TEXT NOT NULL,
  status_reason          TEXT NOT NULL,
  guard_json             TEXT NOT NULL,
  input_hash             TEXT NOT NULL,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (
    metric_version, policy_id, asin, domain_id, series_kind, category_key,
    definition_variant, as_of_utc_date, selection_cutoff
  ),
  CHECK (status <> 'ok' OR value IS NOT NULL),
  CHECK (status = 'ok' OR value IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_amazon_derived_asof
  ON amazon_derived_metric(as_of_utc_date, series_kind, status);

CREATE TRIGGER IF NOT EXISTS amazon_derived_no_update
BEFORE UPDATE ON amazon_derived_metric
BEGIN
  SELECT RAISE(ABORT, 'amazon_derived_metric is append-only; add a new metric_version');
END;

CREATE TRIGGER IF NOT EXISTS amazon_derived_no_delete
BEFORE DELETE ON amazon_derived_metric
BEGIN
  SELECT RAISE(ABORT, 'amazon_derived_metric is append-only');
END;

CREATE TABLE IF NOT EXISTS amazon_eval_link (
  link_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  freeze_id         TEXT NOT NULL,
  evaluation_date   TEXT NOT NULL,
  cutoff_at         TEXT NOT NULL,
  metric_id         INTEGER NOT NULL REFERENCES amazon_derived_metric(metric_id) ON DELETE RESTRICT,
  sku_cluster       TEXT,
  mapping_version   TEXT,
  asin              TEXT NOT NULL,
  domain_id         INTEGER NOT NULL CHECK (domain_id = 1),
  link_status       TEXT NOT NULL,
  leak_excluded     INTEGER NOT NULL CHECK (leak_excluded IN (0,1)),
  note              TEXT NOT NULL,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (freeze_id, evaluation_date, cutoff_at, metric_id)
);

CREATE TRIGGER IF NOT EXISTS amazon_eval_link_no_update
BEFORE UPDATE ON amazon_eval_link
BEGIN
  SELECT RAISE(ABORT, 'amazon_eval_link is immutable');
END;

CREATE TRIGGER IF NOT EXISTS amazon_eval_link_no_delete
BEFORE DELETE ON amazon_eval_link
BEGIN
  SELECT RAISE(ABORT, 'amazon_eval_link is immutable');
END;

CREATE VIEW IF NOT EXISTS amazon_v_pool AS
SELECT
  sku_cluster,
  domain_id,
  display_zh,
  pool_status,
  pool_count,
  recommended_pool_min,
  recommended_pool_max,
  notes
FROM amazon_target_group;

CREATE VIEW IF NOT EXISTS amazon_v_freshness AS
SELECT
  b.source_kind,
  COUNT(DISTINCT r.raw_id) AS raw_payloads,
  MAX(r.retrieved_at) AS last_retrieved_at,
  MAX(r.first_available_to_system) AS last_first_available,
  MAX(o.observed_at) AS last_observed_at
FROM amazon_ingest_batch b
LEFT JOIN amazon_raw_payload r ON r.batch_id = b.batch_id
LEFT JOIN amazon_observation o ON o.raw_id = r.raw_id
GROUP BY b.source_kind;

-- Current label only. Freeze-time reads must use amazon_eval_link, which
-- requires the mapping to have been recorded at or before the cutoff.
CREATE VIEW IF NOT EXISTS amazon_v_metric_current_label AS
SELECT
  m.*,
  map.sku_cluster AS current_sku_cluster,
  map.mapping_version AS current_mapping_version
FROM amazon_derived_metric m
LEFT JOIN amazon_asin_map map
  ON map.asin = m.asin
 AND map.domain_id = m.domain_id
 AND map.is_current = 1;

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES ('amazon_bsr_v1', datetime('now'));

COMMIT;
