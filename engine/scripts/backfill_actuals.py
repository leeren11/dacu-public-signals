#!/usr/bin/env python3
"""Walk-forward public-proxy outcomes. No sales invented, no prediction writes.
Existing complete X counts only. Caller must acquire missing native X buckets.
Never use partial day, incomplete window or percentage growth on a zero baseline.
The stamp JSON/MD adds the daily climb, the frozen call, and other stored
platform rows. Those files do not add a second growth formula.
"""
import argparse,json,math
from datetime import date,timedelta
from rolling_engine import connect,apply_migrate_v4
from director_schema import ROOT,migrate
from director_model import config
from display_names import FREEZE_ID,SKU_PRIMARY_METRIC
from export_daily_md import STAMP
from export_walkforward import endpoint_growth,evaluation_document,fetch_platform_rows,fetch_prediction_context,freeze_block,publish,sku_record

def ranks(values):
    ordered=sorted(range(len(values)),key=lambda i:values[i],reverse=True);out=[0.]*len(values);i=0
    while i<len(ordered):
        j=i+1
        while j<len(ordered) and values[ordered[j]]==values[ordered[i]]:j+=1
        avg=((i+1)+j)/2
        for k in range(i,j):out[ordered[k]]=avg
        i=j
    return out

def spearman(x,y):
    if len(x)<3:return None
    x=ranks(x);y=ranks(y);mx=sum(x)/len(x);my=sum(y)/len(y)
    denom=math.sqrt(sum((v-mx)**2 for v in x)*sum((v-my)**2 for v in y))
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/denom if denom else None

def days(start,end):
    d=date.fromisoformat(start);e=date.fromisoformat(end)
    while d<=e:yield d.isoformat();d+=timedelta(days=1)

def _snapshot(item):
    raw=item.get('snapshot_json')
    if not raw:return {}
    try:
        data=json.loads(raw)
    except (TypeError,ValueError):
        return {}
    return data if isinstance(data,dict) else {}

def evaluate(evaluation_date):
    cal,watch=config();window=cal['evaluations'].get(evaluation_date)
    if not window:raise ValueError('No configured evaluation window')
    if evaluation_date>date.today().isoformat():print('[actual] future checkpoint, pending');return {'status':'pending','evaluation':evaluation_date}
    if window['end']>=evaluation_date:raise ValueError('evaluation must follow last full UTC day')
    profiles=(watch or {}).get('profiles') or {}
    con=connect();apply_migrate_v4(con);migrate(con)
    # Latest complete measurement of each UTC bucket across runs, never partial.
    buckets={}
    for r in con.execute('''select s.*,r.report_ts from signals_daily s join runs r on r.run_id=s.run_id where s.is_partial=0 and s.platform='X' and s.signal_date<? order by r.report_ts''',(evaluation_date,)):
        buckets[(r['metric_key'],r['signal_date'])]=dict(r)
    blocks=[]
    with con:
        fids=[r['freeze_id'] for r in con.execute('select freeze_id from prediction_freeze where as_of_date<?',(window['start'],))]
        for fid in fids:
            freeze=dict(con.execute('select * from prediction_freeze where freeze_id=?',(fid,)).fetchone());fd=date.fromisoformat(freeze['as_of_date'])
            base=list(days((fd-timedelta(days=7)).isoformat(),(fd-timedelta(days=1)).isoformat()))
            target=list(days(window['start'],window['end']))
            items=[dict(r) for r in con.execute('select * from prediction_items where freeze_id=? order by rank_in_list',(fid,))]
            peers={}
            for item in items:
                peers.setdefault(SKU_PRIMARY_METRIC[item['sku_cluster']],[]).append(item['sku_cluster'])
            observations=[]
            for item in items:
                metric=SKU_PRIMARY_METRIC[item['sku_cluster']]
                ts=[buckets.get((metric,d)) for d in target]
                # Baseline observations must be in a run collected no later than freeze day.
                bs=[]
                for d in base:
                    r=con.execute('''select s.* from signals_daily s join runs r on s.run_id=r.run_id where s.metric_key=? and s.signal_date=? and s.platform='X' and s.is_partial=0 and r.as_of_date<=? order by r.report_ts desc limit 1''',(metric,d,freeze['as_of_date'])).fetchone()
                    bs.append(dict(r) if r else None)
                bvals=[None if r is None else r['value'] for r in bs]
                tvals=[None if r is None else r['value'] for r in ts]
                actual,growth=endpoint_growth(bvals,tvals)
                note='Complete X UTC count proxy; relative growth against pre-freeze 7d daily mean; category-proxy ties, not SKU orders.' if growth is not None else 'Pending: missing full evaluation/baseline days or zero baseline; never impute actual.'
                observations.append({'item':item,'metric':metric,'value':actual,'growth':growth,'note':note,'base':base,'bvals':bvals,'target':target,'tvals':tvals,'ts':ts})
                if actual is not None:
                    for r in ts:
                        con.execute('''INSERT INTO actuals_daily(date,platform,metric_key,sku_cluster,value,unit,source_note,is_proxy) VALUES (?,'X',?,?,?,'posts',?,1) ON CONFLICT(date,platform,metric_key,sku_cluster) DO UPDATE SET value=excluded.value,source_note=excluded.source_note''',(r['signal_date'],metric,item['sku_cluster'],r['value'],note))
                con.execute('''INSERT INTO actuals_sku_window(freeze_id,sku_cluster,window_start,window_end,proxy_metric,actual_value,actual_label,notes) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(freeze_id,sku_cluster,proxy_metric,window_start,window_end) DO UPDATE SET actual_value=excluded.actual_value,actual_label=excluded.actual_label,notes=excluded.notes''',(fid,item['sku_cluster'],window['start'],window['end'],metric,actual,'observed' if actual is not None else 'pending',note))
            valid=[o for o in observations if o['growth'] is not None]
            ar=ranks([o['growth'] for o in valid]);pr=ranks([-o['item']['rank_in_list'] for o in valid]);mae=sum(abs(a-p) for a,p in zip(ar,pr))/len(ar) if ar else None
            rho=spearman([-o['item']['rank_in_list'] for o in valid],[o['growth'] for o in valid])
            skus=[]
            for o in observations:
                idx=valid.index(o) if o in valid else None
                item=o['item']
                con.execute('''INSERT INTO walkforward_results(freeze_id,evaluation_date,sku_cluster,window_start,window_end,predicted_rank,actual_value,actual_growth,actual_rank,rank_error,source_note) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(freeze_id,evaluation_date,sku_cluster) DO UPDATE SET actual_value=excluded.actual_value,actual_growth=excluded.actual_growth,actual_rank=excluded.actual_rank,rank_error=excluded.rank_error,source_note=excluded.source_note''',(fid,evaluation_date,item['sku_cluster'],window['start'],window['end'],item['rank_in_list'],o['value'],o['growth'],ar[idx] if idx is not None else None,abs(ar[idx]-pr[idx]) if idx is not None else None,o['note']))
                ctx=fetch_prediction_context(con,fid,item['sku_cluster'],evaluation_date,FREEZE_ID)
                skus.append(sku_record(
                    sku_cluster=item['sku_cluster'],predicted_rank=item['rank_in_list'],predicted_action=item['predicted_action'],
                    metric=o['metric'],shared_with=peers.get(o['metric'],[]),
                    baseline_days=o['base'],baseline_values=o['bvals'],eval_days=o['target'],eval_values=o['tvals'],
                    actual_rank=ar[idx] if idx is not None else None,rank_error=abs(ar[idx]-pr[idx]) if idx is not None else None,
                    source_note=o['note'],
                    scores={'urgency':item.get('predicted_urgency'),'demand':item.get('predicted_demand'),'content':item.get('predicted_content'),'fulfill':item.get('predicted_fulfill'),'total':item.get('predicted_total'),'price_band':item.get('price_band')},
                    snapshot=_snapshot(item),timing=ctx['timing'],checkpoints=ctx['checkpoints'],t0_reference=ctx['t0_reference'],
                    platforms=fetch_platform_rows(con,item['sku_cluster'],window['start'],window['end'],evaluation_date),
                    priors=profiles.get(item['sku_cluster']),
                ))
            note='Public proxy only; rank MAE recomputed on common valid subset; category duplicates not independent. No model calibration until multiple independent windows.'
            con.execute('insert into walkforward_metrics values (?,?,?,?,?,?) ON CONFLICT(freeze_id,evaluation_date) DO UPDATE SET n=excluded.n,spearman=excluded.spearman,rank_mae=excluded.rank_mae,note=excluded.note',(fid,evaluation_date,len(valid),rho,mae,note))
            blocks.append(freeze_block(freeze,skus,rho,mae,note,base[0],base[-1]))
    con.close()
    doc=evaluation_document(evaluation_date,window,blocks,black_friday=(cal.get('anchors') or {}).get('Black_Friday'))
    artifacts=publish(doc,STAMP/'walk-forward',ROOT/'reports')
    doc['artifacts']=artifacts
    print(json.dumps({'evaluation_date':evaluation_date,'summary':doc['summary'],'artifacts':artifacts},ensure_ascii=False))
    return doc
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',required=True);args=ap.parse_args();evaluate(args.as_of)
