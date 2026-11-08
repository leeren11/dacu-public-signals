#!/usr/bin/env python3
"""One local idempotent entry point. No remote push, no routine mutation, no fake X."""
import argparse,json,shutil,sys
from pathlib import Path
from datetime import date
from collect_multi_platform import collect_one
from rolling_engine import connect,compute_rolling_for_as_of,persist_rolling
from export_daily_md import export_one,STAMP
from export_daily_pdf import render_markdown_pdf
from director_schema import ROOT
from director_model import config

def run(as_of,x_input=None,with_catalysts=False,skip_collect=False,amazon_local_input=None):
    if as_of>date.today().isoformat():raise ValueError('Cannot generate future observations')
    if not skip_collect:collect_one(as_of,x_input)
    con=connect();rows,meta,complete,partial,rid=compute_rolling_for_as_of(con,as_of,use_catalysts=with_catalysts);persist_rolling(con,rows,meta);con.close()
    cal,_=config()
    # Evaluate before export so the daily MD can quote real walk-forward numbers.
    wf=None
    if as_of in cal['evaluations']:
        from backfill_actuals import evaluate
        wf=evaluate(as_of)
    md=export_one(as_of,recompute=False);pdf=render_markdown_pdf(md,ROOT/'reports'/f'dacu_daily_{as_of}.pdf')
    (STAMP/'reports').mkdir(exist_ok=True);shutil.copy2(pdf,STAMP/'reports'/pdf.name)
    if as_of==cal['freeze']['T1']:
        from freeze_T1_hard import freeze
        freeze(as_of)
    out={'as_of':as_of,'model':'director_v1','md':str(md),'pdf':str(pdf),'fresh_x':len(complete)}
    if isinstance(wf,dict):
        out['walkforward']={'status':wf.get('status','ok'),'evaluation':wf.get('evaluation_date'),'summary':wf.get('summary'),'artifacts':wf.get('artifacts')}
    # Optional local Keepa file only. Default is a no-op: no live request and no score or freeze write.
    if amazon_local_input:
        from amazon_bsr.local_hook import ingest_local_file
        from rolling_engine import DB_PATH
        out['amazon_bsr']=ingest_local_file(DB_PATH, amazon_local_input)
    print(json.dumps(out,ensure_ascii=False))
    return md,pdf
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',default=date.today().isoformat());ap.add_argument('--x-input');ap.add_argument('--with-catalysts',action='store_true');ap.add_argument('--skip-collect',action='store_true',help='Offline re-render; do not treat as fresh acquisition');ap.add_argument('--amazon-local-input',default=None,help='Optional local Keepa JSON. Never performs live requests and does not change scores or freezes.');a=ap.parse_args();run(a.as_of,a.x_input,a.with_catalysts,a.skip_collect,a.amazon_local_input)
