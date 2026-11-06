#!/usr/bin/env python3
"""Create append-only T1 from that day's Live ranks. Before freeze day: dry-run only."""
import argparse,json,os
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from rolling_engine import connect,apply_migrate_v4,load_persisted_rolling
from director_schema import migrate
from director_model import config
from export_daily_md import table,num,STAMP

def freeze(as_of=None,dry_run=False):
    cal,_=config();target=cal['freeze']['T1'];as_of=as_of or date.today().isoformat()
    con=connect();apply_migrate_v4(con);migrate(con)
    rows=load_persisted_rolling(con,target)
    # Before target, preview latest known Live ranks but never stamp a future forecast.
    if as_of<target or date.today().isoformat()<target or dry_run:
        if not rows:
            last=con.execute('select max(as_of_date) from rolling_runs where formula_version=?',('director_v1',)).fetchone()[0]
            rows=load_persisted_rolling(con,last) if last else []
        print(json.dumps({'status':'dry_run','target':target,'preview':[(r['rolling_rank'],r['zh_name'],r['live_total']) for r in rows]},ensure_ascii=False));con.close();return 'dry_run'
    fid=f'T1_{target}_top9';path=STAMP/'freeze'/f'{fid}_hard.md'
    existing=con.execute('select count(*) from live_freeze_items where freeze_id=?',(fid,)).fetchone()[0]
    if existing:
        if existing!=9 or not path.exists():raise RuntimeError('partial T1 exists; human repair required, never overwrite')
        print(f'[T1] already frozen {path}');con.close();return 'exists'
    if len(rows)!=9 or any(r['live_total'] is None for r in rows):raise RuntimeError('T1 pending: no 9 exact-date Live rows')
    rr=con.execute('select * from rolling_runs where as_of_date=?',(target,)).fetchone()
    if rr['formula_version']!='director_v1':raise RuntimeError('T1 must use director_v1')
    yday=(date.fromisoformat(target)-timedelta(days=1)).isoformat()
    full=con.execute('select count(distinct metric_key) from signals_daily where run_id=? and signal_date=? and is_partial=0',(rr['source_run_id'],yday)).fetchone()[0]
    if full<7:raise RuntimeError('T1 pending: missing complete X bucket')
    # Replayed report after target cannot silently claim it was frozen on target.
    now=datetime.now(timezone(timedelta(hours=8))).isoformat()
    if now[:10]!=target:raise RuntimeError('T1 missed target: refuse retroactive hard freeze; manual explicit late-freeze policy needed')
    text='\n'.join([f'# {fid} · Hard Freeze',f'- frozen_at: {now} Asia/Shanghai',f'- model: director_v1; source_run_id: {rr["source_run_id"]}','- Scores five dimensions /25. T0 immutable and separate.',table(['Rank','中文','English','Live_Score'],[(r['rolling_rank'],r['zh_name'],r['sku_cluster'],num(r['live_total'])) for r in rows]),''])
    # Exclusive write prevents accidental overwrite. DB rollback/file recovery on error.
    with con:
        con.execute('INSERT INTO prediction_freeze(freeze_id,freeze_label,freeze_ts,as_of_date,status,source_run_id,note) VALUES (?,?,?,?,?,?,?)',(fid,'director_v1 hard',now,target,'hard',rr['source_run_id'],'New Live five-dimension baseline; T0 unchanged'))
        for r in rows:
            snap=json.dumps(r,ensure_ascii=False)
            con.execute('insert into live_freeze_items(freeze_id,as_of_date,sku_cluster,predicted_rank,predicted_score,snapshot_json,created_at) values (?,?,?,?,?,?,?)',(fid,target,r['sku_cluster'],r['rolling_rank'],r['live_total'],snap,now))
            con.execute('INSERT INTO prediction_items(freeze_id,sku_cluster,predicted_action,predicted_demand,predicted_content,predicted_fulfill,predicted_total,rank_in_list,snapshot_json) VALUES (?,?,?,?,?,?,?,?,?)',(fid,r['sku_cluster'],'Live hard freeze',r['multi_platform_demand'],r['content_ad_leverage'],r['fulfillment_sla'],r['live_total'],r['rolling_rank'],snap))
        with path.open('x') as f:f.write(text)
    con.close();print(f'[T1] {path}');return 'frozen'
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--as-of');ap.add_argument('--dry-run',action='store_true');a=ap.parse_args();freeze(a.as_of,a.dry_run)
