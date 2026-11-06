-- Non-destructive schema v5. T0 prediction tables untouched.
CREATE TABLE IF NOT EXISTS platform_signals (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(run_id),
 signal_date TEXT NOT NULL, platform TEXT NOT NULL, channel TEXT NOT NULL,
 metric_key TEXT NOT NULL, sku_cluster_or_topic TEXT NOT NULL,
 value REAL, unit TEXT, slope_7d REAL, dod_pct REAL,
 is_partial INTEGER NOT NULL DEFAULT 0 CHECK(is_partial IN(0,1)),
 is_proxy INTEGER NOT NULL DEFAULT 1 CHECK(is_proxy IN(0,1)),
 source_url TEXT NOT NULL, source_note TEXT NOT NULL, as_of_ts TEXT NOT NULL,
 period_start TEXT, period_end TEXT, available_at TEXT,
 status TEXT NOT NULL DEFAULT 'missing',
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 UNIQUE(run_id,platform,channel,metric_key,sku_cluster_or_topic,signal_date)
);
CREATE INDEX IF NOT EXISTS idx_platform_asof ON platform_signals(run_id,platform,signal_date);
CREATE TABLE IF NOT EXISTS live_freeze_items (
 freeze_id TEXT NOT NULL, as_of_date TEXT NOT NULL, sku_cluster TEXT NOT NULL,
 predicted_rank INTEGER NOT NULL, predicted_score REAL NOT NULL, snapshot_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(freeze_id,sku_cluster)
);
CREATE TRIGGER IF NOT EXISTS immutable_live_freeze_update BEFORE UPDATE ON live_freeze_items
 BEGIN SELECT RAISE(ABORT,'Live freeze immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_live_freeze_delete BEFORE DELETE ON live_freeze_items
 BEGIN SELECT RAISE(ABORT,'Live freeze immutable'); END;
CREATE TABLE IF NOT EXISTS walkforward_results (
 freeze_id TEXT NOT NULL, evaluation_date TEXT NOT NULL, sku_cluster TEXT NOT NULL,
 window_start TEXT NOT NULL, window_end TEXT NOT NULL, predicted_rank INTEGER,
 actual_value REAL, actual_growth REAL, actual_rank REAL, rank_error REAL, source_note TEXT,
 PRIMARY KEY(freeze_id,evaluation_date,sku_cluster)
);
CREATE TABLE IF NOT EXISTS walkforward_metrics (
 freeze_id TEXT NOT NULL, evaluation_date TEXT NOT NULL, n INTEGER NOT NULL,
 spearman REAL, rank_mae REAL, note TEXT, PRIMARY KEY(freeze_id,evaluation_date)
);
INSERT OR IGNORE INTO schema_migrations(version) VALUES ('5');
