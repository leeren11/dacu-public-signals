-- dacu-signal schema v4: Dual-Track Rolling Forecast tables
-- Asia/Shanghai; public-proxy only; never invent GMV.
-- Does NOT touch prediction_* freeze fields.
-- Idempotent via IF NOT EXISTS.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS rolling_runs (
  run_id           TEXT PRIMARY KEY,
  as_of_date       TEXT NOT NULL,          -- YYYY-MM-DD
  source_run_id    TEXT NOT NULL,          -- signals/sku_scoring run used
  freeze_id        TEXT NOT NULL DEFAULT 'T0_2026-11-02_top9',
  complete_day     TEXT NOT NULL,          -- latest is_partial=0 day used
  black_friday     TEXT NOT NULL DEFAULT '2026-11-27',
  days_to_bf       INTEGER,
  catalysts_path   TEXT,
  catalysts_as_of  TEXT,
  formula_version  TEXT NOT NULL DEFAULT 'rolling_v1',
  note             TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rolling_sku_scoring (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id           TEXT NOT NULL REFERENCES rolling_runs(run_id) ON DELETE CASCADE,
  as_of_date       TEXT NOT NULL,
  sku_cluster      TEXT NOT NULL REFERENCES sku_catalog(sku_cluster),
  zh_name          TEXT,
  t0_rank          INTEGER NOT NULL,
  t0_urgency       REAL,
  t0_demand        REAL,
  t0_content       REAL,
  t0_fulfill       REAL,
  t0_total         REAL,
  rolling_urgency  REAL NOT NULL,
  rolling_demand   REAL NOT NULL,
  rolling_content  REAL NOT NULL,
  rolling_fulfill  REAL NOT NULL,
  catalyst_adj     REAL NOT NULL DEFAULT 0,
  rolling_total    REAL NOT NULL,
  rolling_rank     INTEGER NOT NULL,
  rank_delta       INTEGER NOT NULL,       -- t0_rank - rolling_rank; + = rose vs T0
  demand_adj       REAL NOT NULL DEFAULT 0,
  fulfill_adj      REAL NOT NULL DEFAULT 0,
  primary_metric   TEXT,
  dod_pct          REAL,
  slope_7d         REAL,
  consec_hot_days  INTEGER,
  action_note      TEXT,
  formula_note     TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(run_id, sku_cluster),
  UNIQUE(run_id, rolling_rank)
);

CREATE INDEX IF NOT EXISTS idx_rolling_sku_asof
  ON rolling_sku_scoring(as_of_date, rolling_rank);

CREATE INDEX IF NOT EXISTS idx_rolling_runs_asof
  ON rolling_runs(as_of_date);
