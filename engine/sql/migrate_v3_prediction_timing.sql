-- dacu-signal schema v3: ferment/peak windows + verify checkpoints for backtest
-- Asia/Shanghai; public-proxy only; never invent GMV.
-- Idempotent via IF NOT EXISTS / guarded ALTER (script also guards).

PRAGMA foreign_keys = ON;

-- 1) Per-SKU ferment / peak / verify_by timing (prediction side; immutable once frozen)
CREATE TABLE IF NOT EXISTS prediction_timing (
  freeze_id            TEXT NOT NULL REFERENCES prediction_freeze(freeze_id) ON DELETE RESTRICT,
  sku_cluster          TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  ferment_window_start TEXT NOT NULL,   -- YYYY-MM-DD 预期公开讨论/种草开始明显抬升
  ferment_window_end   TEXT NOT NULL,
  peak_window_start    TEXT,            -- 可选：预期高峰窗
  peak_window_end      TEXT,
  verify_by_date       TEXT NOT NULL,   -- 最晚用公开代理判定是否成立
  rationale            TEXT NOT NULL,   -- 一句中文：为何这个窗
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (freeze_id, sku_cluster),
  FOREIGN KEY (freeze_id, sku_cluster)
    REFERENCES prediction_items(freeze_id, sku_cluster) ON DELETE RESTRICT
);

-- 2) Discrete verify checkpoints (prediction side; immutable expected_* fields)
CREATE TABLE IF NOT EXISTS prediction_checkpoints (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  freeze_id        TEXT NOT NULL,
  sku_cluster      TEXT NOT NULL,
  checkpoint_date  TEXT NOT NULL,       -- YYYY-MM-DD
  checkpoint_label TEXT NOT NULL,
  expected_signal  TEXT NOT NULL,       -- 预期看到什么公开代理变化
  metric_key       TEXT NOT NULL,       -- 建议对照的 signals_daily / actuals metric
  pass_rule        TEXT NOT NULL,       -- 如何算命中（公开代理，不编 GMV）
  sort_order       INTEGER NOT NULL DEFAULT 1,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (freeze_id, sku_cluster, checkpoint_date, sort_order),
  FOREIGN KEY (freeze_id, sku_cluster)
    REFERENCES prediction_timing(freeze_id, sku_cluster) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_pred_checkpoints_date
  ON prediction_checkpoints(checkpoint_date, freeze_id);

-- 3) Future real evaluations at each checkpoint (empty until eval day)
CREATE TABLE IF NOT EXISTS checkpoint_actuals (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  checkpoint_id    INTEGER NOT NULL REFERENCES prediction_checkpoints(id) ON DELETE RESTRICT,
  freeze_id        TEXT NOT NULL,
  sku_cluster      TEXT NOT NULL,
  checkpoint_date  TEXT NOT NULL,
  actual_value     REAL,
  actual_label     TEXT,               -- up / flat / down / 热度抬升 ...
  hit              INTEGER,            -- 1/0/NULL
  notes            TEXT,
  evaluated_at     TEXT,
  UNIQUE (checkpoint_id),
  UNIQUE (freeze_id, sku_cluster, checkpoint_date)
);

-- 4) timing_hit on backtest_logs (NULL = pending; filled post verify_by)
-- Applied by Python with PRAGMA table_info guard (SQLite no IF NOT EXISTS on ADD COLUMN).

-- 5) Immutable prediction timing fields
CREATE TRIGGER IF NOT EXISTS trg_prediction_timing_no_update_preds
BEFORE UPDATE OF
  freeze_id, sku_cluster,
  ferment_window_start, ferment_window_end,
  peak_window_start, peak_window_end,
  verify_by_date, rationale
ON prediction_timing
BEGIN
  SELECT RAISE(ABORT, 'prediction_timing fields are immutable; create a new freeze_id');
END;

CREATE TRIGGER IF NOT EXISTS trg_prediction_checkpoints_no_update_preds
BEFORE UPDATE OF
  freeze_id, sku_cluster, checkpoint_date, checkpoint_label,
  expected_signal, metric_key, pass_rule, sort_order
ON prediction_checkpoints
BEGIN
  SELECT RAISE(ABORT, 'prediction_checkpoints prediction fields are immutable; create a new freeze_id');
END;

-- 6) View: timing + checkpoints vs actuals (pending until filled)
DROP VIEW IF EXISTS v_timing_backtest;
CREATE VIEW v_timing_backtest AS
SELECT
  pf.freeze_id,
  pf.status AS freeze_status,
  pf.as_of_date AS freeze_as_of,
  pi.rank_in_list,
  pi.sku_cluster,
  pi.predicted_action,
  pt.ferment_window_start,
  pt.ferment_window_end,
  pt.peak_window_start,
  pt.peak_window_end,
  pt.verify_by_date,
  pt.rationale,
  pc.id AS checkpoint_id,
  pc.checkpoint_date,
  pc.checkpoint_label,
  pc.expected_signal,
  pc.metric_key,
  pc.pass_rule,
  pc.sort_order,
  CASE
    WHEN ca.actual_value IS NULL AND ca.actual_label IS NULL AND ca.hit IS NULL THEN 'pending'
    ELSE 'filled'
  END AS checkpoint_actual_status,
  ca.actual_value,
  ca.actual_label,
  ca.hit AS checkpoint_hit,
  ca.notes AS checkpoint_notes,
  ca.evaluated_at AS checkpoint_evaluated_at,
  bl.timing_hit AS sku_timing_hit,
  bl.hit AS action_hit,
  bl.actual_label AS sku_actual_label
FROM prediction_freeze pf
JOIN prediction_items pi
  ON pi.freeze_id = pf.freeze_id
JOIN prediction_timing pt
  ON pt.freeze_id = pi.freeze_id AND pt.sku_cluster = pi.sku_cluster
JOIN prediction_checkpoints pc
  ON pc.freeze_id = pt.freeze_id AND pc.sku_cluster = pt.sku_cluster
LEFT JOIN checkpoint_actuals ca
  ON ca.checkpoint_id = pc.id
LEFT JOIN backtest_logs bl
  ON bl.freeze_id = pi.freeze_id AND bl.sku_cluster = pi.sku_cluster;

-- 7) Compact one-row-per-SKU timing summary
DROP VIEW IF EXISTS v_timing_summary;
CREATE VIEW v_timing_summary AS
SELECT
  pi.rank_in_list,
  pt.freeze_id,
  pt.sku_cluster,
  pi.predicted_action,
  pt.ferment_window_start || ' ~ ' || pt.ferment_window_end AS ferment_window,
  CASE
    WHEN pt.peak_window_start IS NULL THEN NULL
    ELSE pt.peak_window_start || ' ~ ' || pt.peak_window_end
  END AS peak_window,
  pt.verify_by_date,
  (SELECT MIN(checkpoint_date) FROM prediction_checkpoints x
   WHERE x.freeze_id = pt.freeze_id AND x.sku_cluster = pt.sku_cluster) AS first_checkpoint,
  (SELECT GROUP_CONCAT(checkpoint_date, ', ') FROM prediction_checkpoints y
   WHERE y.freeze_id = pt.freeze_id AND y.sku_cluster = pt.sku_cluster) AS checkpoint_dates,
  pt.rationale,
  bl.timing_hit,
  CASE WHEN bl.timing_hit IS NULL THEN 'pending' ELSE 'filled' END AS timing_status
FROM prediction_timing pt
JOIN prediction_items pi
  ON pi.freeze_id = pt.freeze_id AND pi.sku_cluster = pt.sku_cluster
LEFT JOIN backtest_logs bl
  ON bl.freeze_id = pt.freeze_id AND bl.sku_cluster = pt.sku_cluster;
