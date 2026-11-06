#!/usr/bin/env python3
"""Shared director_v1 report data; Markdown is also the exact PDF input."""
import argparse,json
from pathlib import Path
from datetime import date
from rolling_engine import connect,apply_migrate_v4,compute_rolling_for_as_of,persist_rolling,pick_run,build_yesterday_complete_table,build_partial_table,load_persisted_rolling,shanghai_now_iso
from director_schema import ROOT,migrate
from director_model import platform_rows,config
STAMP=Path('/workspace/dacu-public-signals-stamp')
def num(v,digits=1):return '—' if v is None else f'{v:.{digits}f}'
def esc(v):return str(v if v is not None else '—').replace('|','/').replace('\n',' ')
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(esc(v) for v in row)+' |' for row in rows])
def report(as_of,recompute=True):
    con=connect();apply_migrate_v4(con);migrate(con)
    run=pick_run(con,as_of);rid=run['run_id']
    if recompute:
        rows,meta,complete,partial,_=compute_rolling_for_as_of(con,as_of);persist_rolling(con,rows,meta);rolling=[r.__dict__ for r in rows]
    else:
        rolling=load_persisted_rolling(con,as_of)
        if not rolling or rolling[0]['live_total'] is None:raise ValueError('Run director_v1 scoring first')
        complete,_=build_yesterday_complete_table(con,rid,as_of);partial=build_partial_table(con,rid,as_of)
    signals=platform_rows(con,rid);cal,watch=config()
    out=[f'# 大促公开信号日更 · {as_of}','',f'- 模型：director_v1 / schema v5；source_run_id：{rid}',f'- 原采集报告时间：{run["report_ts"]}（Asia/Shanghai）；本次重绘：{shanghai_now_iso()}（Asia/Shanghai）','- 历史重建：仅使用截至报告日已发布的背景与该run原有X完整日桶；当前抓取历史缺口不伪造。','- T0四维 /20 vs Live五维 /25：量纲不同，不能把分数差解释为增长率。Rank_Delta = T0_Rank − Rolling_Rank。','- 非GMV/订单/实测ROI；仓储、毛利、退货率、视觉钩子、白牌优势为明确的分析师情景先验。缺测不是0需求。','- 本窗独立采集计算；大促日更工作台只读；外部催化权重按 pipeline `--with-catalysts` 启用（历史重绘可 overlay，不伪造日桶）。','','## 零售日历', '',table(['锚点','日期','距离天数'],[(k,v,(date.fromisoformat(v)-date.fromisoformat(as_of)).days) for k,v in cal['anchors'].items()]),'','## 信号（昨日完整 is_partial=0 · 去RT · UTC日桶）','',table(['指标','实际UTC日桶','完整值','较前一日 DoD%','slope_7d','有效完整桶N'],[(r['label'],r['signal_date'],num(r['value'],0),num(r['dod_pct'])+'%' if r['dod_pct'] is not None else '—',num(r['slope_7d'],4),r.get('window_n','—')) for r in complete]),'','> DoD严格对前一日；OLS使用最近7个自然日内的完整桶与真实日期间距，不掺partial。缺昨日会标明实际最新日期；缺测不补0。','']
    if not complete:out+=['**缺口：无该run完整X桶；不是零需求。请用原生X connector抓取后重跑。**','']
    if partial:out+=['## 今日partial（is_partial=1，不参与评分）','',table(['指标','UTC日期','partial值','库内slope（仅留档）'],[(r['label'],r['signal_date'],num(r['value'],0),num(r['slope_7d'],4)) for r in partial]),'']
    out+=['## 跨平台信号摘要','',table(['平台','行数','有数值','NULL缺口','仅月度背景'],[(p,len(rs:= [r for r in signals if r['platform']==p]),sum(r['value'] is not None for r in rs),sum(r['value'] is None for r in rs),sum(r['status']=='context' for r in rs)) for p in sorted({r['platform'] for r in signals})]),'','### 跨平台明细（仅有数值行；空行已折叠）','']
    measured=[r for r in signals if r['value'] is not None and r.get('status')!='snapshot']
    if measured:
        out+=[table(['平台/渠道','SKU或话题','真实窗口','数值/单位','DoD%','slope_7d','状态'],[(r['platform']+'/'+r['channel'],r['sku_cluster_or_topic'],f"{r['period_start'] or r['signal_date']}..{r['period_end'] or r['signal_date']}",f"{num(r['value'])} {r['unit']}",num(r['dod_pct']),num(r['slope_7d'],4),r['status']+(' / partial' if r['is_partial'] else '')+(' / proxy' if r['is_proxy'] else ' / API')) for r in measured]),'']
    else:
        out+=['（本日无跨平台有数值观测；见下方折叠摘要。）','']
    # One-line omit summary per platform instead of wall of unavailable rows.
    omit_rows=[]
    for p in sorted({r['platform'] for r in signals}):
        rs=[r for r in signals if r['platform']==p]
        empty=[r for r in rs if r['value'] is None]
        if not empty: continue
        reasons=[]
        for r in empty:
            note=(r.get('source_note') or '')
            tag='NULL'
            for key in ('HTTP 403','HTTP 429','HTTP 401','login','blocked','backoff','no dated','No public','Could not','unavailable','pytrends','empty'):
                if key.lower() in note.lower():
                    tag=key;break
            reasons.append(tag)
        # majority reason
        from collections import Counter
        top=Counter(reasons).most_common(1)[0][0]
        omit_rows.append((p,f"{sum(r['value'] is not None for r in rs)}/{len(rs)} measured",f"{top} — omitted {len(empty)} empty rows"))
    if omit_rows:
        out+=['#### 缺测折叠摘要（禁止打印 unavailable 空行）','',table(['平台','有数值/总行','说明'],omit_rows),'']
    out+=['### 公开来源与缺口说明（每平台一行）','']
    by_plat={}
    for r in signals:
        p=r['platform']
        # Prefer a measured note; else first gap note.
        if p not in by_plat or (r['value'] is not None and by_plat[p]['value'] is None):
            by_plat[p]=r
    for p in sorted(by_plat):
        r=by_plat[p]
        note=(r['source_note'] or '')
        if len(note)>220: note=note[:217]+'...'
        out.append(f"- {p}/{r['channel']}: {note} 来源：{r['source_url']}；抓取：{r['as_of_ts']}；已发布：{r['available_at'] or '未能核实'}")
    out+=['','## Top9 双轨 T0 vs Live Rolling','',table(['Rolling_Rank','T0_Rank','Rank_Delta','中文名','English SKU','T0_Score /20','Live_Rolling_Score /25','外部催化'],[(r['rolling_rank'],r['t0_rank'],f"{r['rank_delta']:+}",r['zh_name'],r['sku_cluster'],num(r['t0_total']),num(r['live_total']),num(r['catalyst_adj'])) for r in rolling]),'','### 五维评分（各0–5，一位小数）','',table(['SKU中文','需求D','内容买量C','履约F','净利退货M','白牌W'],[(r['zh_name'],num(r['multi_platform_demand']),num(r['content_ad_leverage']),num(r['fulfillment_sla']),num(r['margin_return_risk']),num(r['white_label_viability'])) for r in rolling]),'']
    catalog={r['sku_cluster']:r['parent_category'] for r in con.execute('select sku_cluster,parent_category from sku_catalog')}
    cats={catalog.get(r['sku_cluster'],'Other') for r in rolling}
    cols=['multi_platform_demand','content_ad_leverage','fulfillment_sla','margin_return_risk','white_label_viability','live_total']
    out+=['## 类目Live五维（所属SKU等权均值，不再复制T0）','',table(['类目','需求D','内容C','履约F','风险M','白牌W','Live均分'],[(c,*[num(sum(r[k] for r in rolling if catalog.get(r['sku_cluster'],'Other')==c)/sum(catalog.get(r['sku_cluster'],'Other')==c for r in rolling)) for k in cols]) for c in sorted(cats)]),'']
    from export_walkforward import daily_section
    wf=daily_section(as_of,STAMP/'walk-forward',con)
    if wf:out+=['',wf,'']
    out+=['## 评分可审计说明','']
    for r in rolling:
        _n=r['formula_note']
        out.append('- '+r['zh_name']+': '+(_n if len(_n)<=280 else _n[:277]+'...'))
    out+=['','## 冻结与回测','- T0：freeze/T0_2026-11-02_top9.md，原分数/排名/预测字段不修改。','- T1：11/08基于当日最新director_v1滚动排名硬冻结；提前执行只dry-run；一旦生成不可覆盖。','- 11/12与12/01：先 evaluate 再导出。逐日爬坡、冻结动作与公开对照写入 walk-forward/walkforward_<评估日>.md；没有完整窗口就 pending，不编 actual。','- 先验尚未以多窗口actual自校准；现阶段仅建议低预算轻测，不据代理帖量重仓。','']
    con.close();return '\n'.join(out)
def export_one(as_of,out_dir=STAMP/'daily',recompute=True):
    text=report(as_of,recompute);out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True);path=out_dir/f'{as_of}.md';path.write_text(text);print(f'[md] {path}');return path
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',required=True);ap.add_argument('--out-dir',default=str(STAMP/'daily'));ap.add_argument('--no-recompute',action='store_true');a=ap.parse_args();export_one(a.as_of,a.out_dir,not a.no_recompute)
