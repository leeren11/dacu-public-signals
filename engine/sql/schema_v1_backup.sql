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
