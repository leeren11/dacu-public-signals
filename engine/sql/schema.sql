-- dacu-signal schema v1
-- Asia/Shanghai calendar dates; public-proxy signals only; never invent GMV.
-- SQLite 3.x

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
  run_id         TEXT PRIMARY KEY,
  run_type       TEXT NOT NULL CHECK (run_type IN ('scheduled','ad_hoc')),
  report_ts      TEXT NOT NULL,          -- Asia/Shanghai ISO-ish, e.g. 2026-11-02T14:59:00+08:00
  as_of_date     TEXT NOT NULL,          -- YYYY-MM-DD Asia/Shanghai
  window_note    TEXT,
  freeze_status  TEXT NOT NULL DEFAULT 'none'
                   CHECK (freeze_status IN ('none','soft','hard')),
  notes          TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS calendar_anchors (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id         TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  anchor_name    TEXT NOT NULL,
  anchor_date    TEXT NOT NULL,         -- YYYY-MM-DD
  days_to_anchor INTEGER,               -- snapshot vs as_of_date of run
  note           TEXT,
  UNIQUE(run_id, anchor_name)
);

CREATE TABLE IF NOT EXISTS sku_catalog (
  sku_cluster    TEXT PRIMARY KEY,
  parent_category TEXT,
  price_band_usd TEXT,
  fulfill_note   TEXT,
  active         INTEGER NOT NULL DEFAULT 1,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signals_daily (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id         TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  signal_date    TEXT NOT NULL,         -- YYYY-MM-DD Asia/Shanghai
  platform       TEXT NOT NULL,         -- X / TikTok / Meta / IG_Threads ...
  metric_key     TEXT NOT NULL,         -- e.g. bfcm_posts, jewelry_gift_posts
  value          REAL NOT NULL,         -- post volume or other proxy
  slope_7d       REAL,                  -- optional day-over-window slope
  unit           TEXT NOT NULL DEFAULT 'posts',
  source_note    TEXT,
  as_of_ts       TEXT,                  -- when scraped
  is_partial     INTEGER NOT NULL DEFAULT 0 CHECK (is_partial IN (0,1)),
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(run_id, signal_date, platform, metric_key)
);

CREATE TABLE IF NOT EXISTS category_scoring (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id           TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  as_of_date       TEXT NOT NULL,
  category         TEXT NOT NULL,
  urgency          REAL NOT NULL,
  demand           REAL NOT NULL,
  content          REAL NOT NULL,
  fulfill          REAL NOT NULL,
  total            REAL NOT NULL,
  emotion_proxy    TEXT,
  action           TEXT NOT NULL,
  rank_hint        INTEGER,
  notes            TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(run_id, as_of_date, category)
);

CREATE TABLE IF NOT EXISTS sku_scoring (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id           TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  as_of_date       TEXT NOT NULL,
  sku_cluster      TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  urgency          REAL,                -- may inherit from parent category
  demand           REAL,
  content          REAL,
  fulfill          REAL,
  total            REAL,
  emotion_proxy    TEXT,
  action           TEXT NOT NULL,       -- 测款 / 测款+预热 / 轻测 / 内容预热 / 观望 / 只清不补 ...
  rank_hint        INTEGER,
  price_band_usd   TEXT,
  notes            TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(run_id, as_of_date, sku_cluster)
);

-- Optional denormalized daily action summary (run + sku → action)
CREATE TABLE IF NOT EXISTS actions_daily (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id         TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  as_of_date     TEXT NOT NULL,
  sku_cluster    TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  action         TEXT NOT NULL,
  priority       INTEGER,
  summary        TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(run_id, as_of_date, sku_cluster)
);

-- Soft/hard freeze plans (T0); no fabricated actuals
CREATE TABLE IF NOT EXISTS freeze_plan (
  freeze_id      TEXT PRIMARY KEY,
  planned_start  TEXT NOT NULL,        -- YYYY-MM-DD
  planned_end    TEXT NOT NULL,
  freeze_kind    TEXT NOT NULL CHECK (freeze_kind IN ('soft','hard')),
  linked_run_id  TEXT REFERENCES runs(run_id),
  status         TEXT NOT NULL DEFAULT 'planned'
                   CHECK (status IN ('planned','active','closed','cancelled')),
  notes          TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backtest_logs (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  freeze_id            TEXT REFERENCES freeze_plan(freeze_id),
  t0_run_id            TEXT REFERENCES runs(run_id),
  as_of_date           TEXT NOT NULL,   -- evaluation date
  sku_cluster          TEXT NOT NULL,
  predicted_action     TEXT,
  predicted_score      REAL,
  actual_proxy_metric  TEXT,            -- e.g. X jewelry_gift posts slope
  actual_value         REAL,            -- NULL until real post-window eval
  error_bucket         TEXT,            -- 信号滞后 / 履约误判 / 噪音 / ...
  notes                TEXT,
  evaluated_at         TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signals_date ON signals_daily(signal_date, platform, metric_key);
CREATE INDEX IF NOT EXISTS idx_sku_scoring_date ON sku_scoring(as_of_date, action);
CREATE INDEX IF NOT EXISTS idx_category_scoring_date ON category_scoring(as_of_date);
CREATE INDEX IF NOT EXISTS idx_backtest_freeze ON backtest_logs(freeze_id, as_of_date);


-- === v2 prediction freeze / actuals (see migrate_v2_prediction_freeze.sql) ===
-- Greenfield installs: apply migrate_v2_prediction_freeze.sql, OR apply the DDL below
-- then rename backtest_logs_v2 → backtest_logs after dropping empty legacy backtest_logs.

-- dacu-signal schema v2: prediction freeze + future actuals + backtest scaffolding
-- Asia/Shanghai; public-proxy only; never invent GMV.
-- Idempotent (IF NOT EXISTS / guarded ALTER).

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

