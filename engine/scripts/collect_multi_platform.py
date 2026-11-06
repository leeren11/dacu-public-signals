#!/usr/bin/env python3
"""Acquire public sources once, idempotently upsert dated observations and NULL gaps."""
import argparse,json,sqlite3
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from rolling_engine import connect,apply_migrate_v4,pick_run,build_yesterday_complete_table
from director_schema import migrate,ROOT
from collectors.public_sources import collect

def ensure_run(con,as_of):
    try: return dict(pick_run(con,as_of))
    except SystemExit:
        rid=f'{as_of}_scheduled_director'
        now=datetime.now(timezone(timedelta(hours=8))).isoformat()
        con.execute('INSERT INTO runs(run_id,run_type,report_ts,as_of_date,notes) VALUES (?,?,?,?,?)',(rid,'scheduled',now,as_of,'director_v1; fresh X buckets required from sanctioned X connector; never copy old counts'))
        con.commit();return dict(pick_run(con,as_of))

def ingest_x(con,run,input_path):
    """Native X connector count export contract. Input contains authoritative UTC buckets.
    [{metric_key,signal_date,value,is_partial,source_note,as_of_ts}]. Never tokens/credentials.
    """
    if not input_path:return
    from display_names import METRIC_ORDER
    items=json.loads(Path(input_path).read_text())
    if isinstance(items,dict) and 'parsed_detail' in items:
        # Backward-compatible with the current native-connector export payload.
        payload=items;items=[]
        watch=json.loads((ROOT/'config/watch_topics.json').read_text())
        for metric,series in payload['parsed_detail'].items():
            for day,point in series.items():
                partial=point['is_partial']
                if point.get('start') and point.get('end'):
                    start=datetime.fromisoformat(point['start'].replace('Z','+00:00'));end=datetime.fromisoformat(point['end'].replace('Z','+00:00'))
                    # X recent-count windows may truncate the oldest edge bucket.
                    if start.hour or start.minute or start.second or (end-start).total_seconds()!=86400:
                        partial=1
                items.append(dict(metric_key=metric,signal_date=day,value=point['count'],is_partial=partial,source_note='Native X connector, UTC buckets, -is:retweet; query='+watch['x_queries'].get(metric,metric),as_of_ts=payload.get('scrape_ts') or run['report_ts']))
    if not isinstance(items,list):raise ValueError('X input must be native parsed_detail export or list of buckets')
    for item in items:
        if item['metric_key'] not in METRIC_ORDER:raise ValueError('unconfigured X metric')
        day=date.fromisoformat(item['signal_date'])
        if day>date.fromisoformat(run['as_of_date']):raise ValueError('future X bucket')
        if item['value']<0 or item['is_partial'] not in (0,1) or not item.get('source_note'):raise ValueError('invalid native X observation')
        if day.isoformat()==run['as_of_date'] and item['is_partial']==0:raise ValueError('current UTC day cannot be complete')
        con.execute('''INSERT INTO signals_daily(run_id,signal_date,platform,metric_key,value,unit,source_note,as_of_ts,is_partial)
          VALUES (?,?,?,?,?,'posts',?,?,?) ON CONFLICT(run_id,signal_date,platform,metric_key)
          DO UPDATE SET value=excluded.value,source_note=excluded.source_note,as_of_ts=excluded.as_of_ts,is_partial=excluded.is_partial''',
          (run['run_id'],item['signal_date'],'X',item['metric_key'],item['value'],item['source_note'],item['as_of_ts'],item['is_partial']))
    con.commit()

def collect_one(as_of,x_input=None):
    # Reuse only this date's native export, never yesterday's file.
    same_day=ROOT/'db'/f'x_counts_{as_of}.json'
    if not x_input and same_day.exists():x_input=same_day
    con=connect();apply_migrate_v4(con);migrate(con);run=ensure_run(con,as_of);ingest_x(con,run,x_input)
    watch=json.loads((ROOT/'config/watch_topics.json').read_text())
    rows=collect(as_of,watch)
    complete,day=build_yesterday_complete_table(con,run['run_id'],as_of)
    for r in complete:
        rows.append(dict(signal_date=r['signal_date'],platform='X',channel='complete_utc',metric_key=r['metric_key'],sku_cluster_or_topic=r['metric_key'],value=r['value'],unit='posts',slope_7d=r['slope_7d'],dod_pct=r['dod_pct'],is_partial=0,is_proxy=0,source_url='https://docs.x.com/x-api/posts/counts/introduction',source_note='Existing native X API counts in signals_daily; original run provenance retained. Count metric is a demand proxy, not orders.',as_of_ts=run['report_ts'],period_start=r['signal_date'],period_end=r['signal_date'],available_at=as_of,status='observed'))
    # Explicit X holes for unattended operation without fresh native connector input.
    from display_names import METRIC_ORDER
    for metric in set(METRIC_ORDER)-{r['metric_key'] for r in complete}:
        rows.append(dict(signal_date=(date.fromisoformat(as_of)-timedelta(days=1)).isoformat(),platform='X',channel='complete_utc',metric_key=metric,sku_cluster_or_topic=metric,value=None,unit='posts',slope_7d=None,dod_pct=None,is_partial=0,is_proxy=0,source_url='https://docs.x.com/x-api/posts/counts/introduction',source_note='No fresh native X connector complete bucket for this run. Supply --x-input; prior run is not copied.',as_of_ts=run['report_ts'],status='missing'))
    # Recompute per-series DoD and calendar-aware slope only from observed complete
    # daily measurements in the SAME metric/unit/source; context never leaks in.
    from rolling_engine import metric_features
    for row in rows:
        if row['platform']=='X' or row['value'] is None or row['status']!='observed' or row['is_partial']:
            continue
        prior=con.execute("""SELECT p.signal_date,p.value FROM platform_signals p JOIN runs r ON r.run_id=p.run_id
          WHERE p.platform=? AND p.channel=? AND p.metric_key=? AND p.sku_cluster_or_topic=?
          AND p.unit=? AND p.status='observed' AND p.is_partial=0 AND p.signal_date<?
          AND r.as_of_date<=? ORDER BY r.report_ts""",(row['platform'],row['channel'],row['metric_key'],row['sku_cluster_or_topic'],row['unit'],row['signal_date'],as_of)).fetchall()
        series={p['signal_date']:p['value'] for p in prior};series[row['signal_date']]=row['value']
        _,dod,slope,_=metric_features(sorted(series.items()),row['signal_date'])
        row['dod_pct']=dod;row['slope_7d']=slope
    cols=['run_id' ,'signal_date','platform','channel','metric_key','sku_cluster_or_topic','value','unit','slope_7d','dod_pct','is_partial','is_proxy','source_url','source_note','as_of_ts','period_start','period_end','available_at','status']
    with con:
        for row in rows:
            row['run_id']=run['run_id']
            conflict='run_id,platform,channel,metric_key,sku_cluster_or_topic,signal_date'
            updates=','.join(f'{c}=excluded.{c}' for c in cols if c not in conflict.split(','))
            con.execute(f"INSERT INTO platform_signals({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT({conflict}) DO UPDATE SET {updates}",[row.get(c) for c in cols])
    counts=[dict(r) for r in con.execute('SELECT platform,count(*) AS rows,count(value) AS measured,sum(value IS NULL) AS gaps FROM platform_signals WHERE run_id=? GROUP BY platform',(run['run_id'],))]
    con.close();print(json.dumps({'as_of':as_of,'counts':counts},ensure_ascii=False));return counts
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',required=True);ap.add_argument('--x-input');args=ap.parse_args();collect_one(args.as_of,args.x_input)
