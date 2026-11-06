"""Idempotent v5 extension; only additive migration, no prediction writes."""
from pathlib import Path
ROOT=Path('/workspace/dacu-signal')
def migrate(con):
    con.executescript((ROOT/'sql/migrate_v5_director.sql').read_text())
    columns={r[1] for r in con.execute('PRAGMA table_info(rolling_sku_scoring)')}
    for name in ('multi_platform_demand','content_ad_leverage','fulfillment_sla','margin_return_risk','white_label_viability','live_total'):
        if name not in columns:
            con.execute(f'ALTER TABLE rolling_sku_scoring ADD COLUMN {name} REAL')
    con.commit()
