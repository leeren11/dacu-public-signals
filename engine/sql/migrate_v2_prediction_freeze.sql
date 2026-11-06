-- dacu-signal schema v2: prediction freeze + future actuals + backtest scaffolding
-- Asia/Shanghai; public-proxy only; never invent GMV.
-- Idempotent when applied via freeze_top9 script (IF NOT EXISTS / guarded ALTER).

PRAGMA foreign_keys = ON;

-- 1) Freeze header (immutable prediction baseline)
CREATE TABLE IF NOT EXISTS prediction_freeze (
  freeze_id     TEXT PRIMARY KEY,
  freeze_label  TEXT NOT NULL,
  freeze_ts     TEXT NOT NULL,          -- Asia/Shanghai ISO, e.g. 2026-11-02T17:05:00+08:00
  as_of_date    TEXT NOT NULL,          -- YYYY-MM-DD
  status        TEXT NOT NULL CHECK (status IN ('soft','hard')),
  source_run_id TEXT REFERENCES runs(run_id),
  note          TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2) Freeze line items (prediction side; do NOT UPDATE prediction fields)
CREATE TABLE IF NOT EXISTS prediction_items (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  freeze_id           TEXT NOT NULL REFERENCES prediction_freeze(freeze_id) ON DELETE RESTRICT,
  sku_cluster         TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  predicted_action    TEXT NOT NULL,
  predicted_urgency   REAL,
  predicted_demand    REAL,
  predicted_content   REAL,
  predicted_fulfill   REAL,
  predicted_total     REAL,
  price_band          TEXT,
  rank_in_list        INTEGER NOT NULL,
  snapshot_json       TEXT,
  frozen_at           TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(freeze_id, sku_cluster),
  UNIQUE(freeze_id, rank_in_list)
);

-- Immutable prediction fields: only new freeze_id allowed for rule changes
CREATE TRIGGER IF NOT EXISTS trg_prediction_items_no_update_preds
BEFORE UPDATE OF
  predicted_action, predicted_urgency, predicted_demand,
  predicted_content, predicted_fulfill, predicted_total,
  price_band, rank_in_list, snapshot_json, sku_cluster, freeze_id
ON prediction_items
BEGIN
  SELECT RAISE(ABORT, 'prediction_items prediction fields are immutable; create a new freeze_id');
END;

CREATE TRIGGER IF NOT EXISTS trg_prediction_freeze_no_update_core
BEFORE UPDATE OF freeze_id, freeze_ts, as_of_date, status, source_run_id
ON prediction_freeze
BEGIN
  SELECT RAISE(ABORT, 'prediction_freeze core fields are immutable; create a new freeze_id');
END;

-- 3) Future real public-proxy actuals (empty until post-window ingest)
CREATE TABLE IF NOT EXISTS actuals_daily (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  date          TEXT NOT NULL,          -- YYYY-MM-DD Asia/Shanghai
  platform      TEXT NOT NULL,
  metric_key    TEXT NOT NULL,
  sku_cluster   TEXT,                   -- NULL = platform-level signal
  value         REAL NOT NULL,
  unit          TEXT NOT NULL DEFAULT 'posts',
  source_note   TEXT,
  is_proxy      INTEGER NOT NULL DEFAULT 1 CHECK (is_proxy IN (0,1)),
  ingested_at   TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(date, platform, metric_key, sku_cluster)
);

CREATE INDEX IF NOT EXISTS idx_actuals_daily_date ON actuals_daily(date, platform, metric_key);

-- 4) Per-SKU window actuals keyed to a freeze
CREATE TABLE IF NOT EXISTS actuals_sku_window (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  freeze_id      TEXT NOT NULL REFERENCES prediction_freeze(freeze_id) ON DELETE RESTRICT,
  sku_cluster    TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  window_start   TEXT NOT NULL,
  window_end     TEXT NOT NULL,
  proxy_metric   TEXT NOT NULL,
  actual_value   REAL,
  actual_label   TEXT,                  -- 热度抬升 / 持平 / 回落 ...
  notes          TEXT,
  ingested_at    TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(freeze_id, sku_cluster, proxy_metric, window_start, window_end)
);

-- 5) Recreate backtest_logs with full compare columns (table currently empty / safe)
-- Keep a compatibility shadow: if old table has rows, migration script copies them.
CREATE TABLE IF NOT EXISTS backtest_logs_v2 (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  freeze_id            TEXT NOT NULL REFERENCES prediction_freeze(freeze_id) ON DELETE RESTRICT,
  t0_run_id            TEXT REFERENCES runs(run_id),
  as_of_date           TEXT,            -- evaluation date; NULL until evaluated
  sku_cluster          TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  predicted_action     TEXT NOT NULL,
  predicted_total      REAL,
  predicted_score      REAL,            -- legacy alias of predicted_total
  actual_proxy_metric  TEXT,
  actual_value         REAL,            -- NULL until real post-window eval; never invent GMV
  actual_label         TEXT,
  hit                  INTEGER,         -- 1/0/NULL (NULL = pending)
  error_bucket         TEXT,            -- 信号滞后 / 履约误判 / 噪音 / ...
  notes                TEXT,
  evaluated_at         TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(freeze_id, sku_cluster)
);

CREATE INDEX IF NOT EXISTS idx_backtest_v2_freeze ON backtest_logs_v2(freeze_id, sku_cluster);

-- 6) View: prediction vs actual at a glance
CREATE VIEW IF NOT EXISTS v_prediction_vs_actual AS
SELECT
  pf.freeze_id,
  pf.freeze_label,
  pf.status AS freeze_status,
  pf.as_of_date AS freeze_as_of,
  pi.rank_in_list,
  pi.sku_cluster,
  pi.predicted_action,
  pi.predicted_total,
  pi.price_band,
  bl.actual_proxy_metric,
  bl.actual_value,
  bl.actual_label,
  CASE
    WHEN bl.actual_value IS NULL AND bl.actual_label IS NULL THEN 'pending'
    ELSE 'filled'
  END AS actual_status,
  bl.hit,
  bl.error_bucket,
  bl.notes AS backtest_notes,
  bl.evaluated_at,
  asw.proxy_metric AS window_proxy_metric,
  asw.actual_value AS window_actual_value,
  asw.actual_label AS window_actual_label,
  asw.window_start,
  asw.window_end
FROM prediction_freeze pf
JOIN prediction_items pi ON pi.freeze_id = pf.freeze_id
LEFT JOIN backtest_logs_v2 bl
  ON bl.freeze_id = pi.freeze_id AND bl.sku_cluster = pi.sku_cluster
LEFT JOIN actuals_sku_window asw
  ON asw.freeze_id = pi.freeze_id AND asw.sku_cluster = pi.sku_cluster;

