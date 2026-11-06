"""director_v1: five independent dimensions; T0 is a comparison only.
No missing platform converted to zero volume. Monthly context is never daily resonance.
"""
import json,math
from datetime import date,timedelta
from director_schema import ROOT,migrate
from display_names import SKU_PRIMARY_METRIC,zh_name,FREEZE_ID

def config():
    return (json.loads((ROOT/'config/retail_calendar.json').read_text()),json.loads((ROOT/'config/watch_topics.json').read_text()))
def clip(x,low=0,high=5):return max(low,min(high,x))
def platform_rows(con,rid):
    return [dict(r) for r in con.execute('SELECT * FROM platform_signals WHERE run_id=? ORDER BY platform,channel,sku_cluster_or_topic',(rid,))]
def eligible(row,sku,as_of):
    return row['sku_cluster_or_topic'] in (sku,'*') and row['value'] is not None and row['status']=='observed' and not row['is_partial'] and row['signal_date']<as_of and row['signal_date']>=(date.fromisoformat(as_of)-timedelta(days=7)).isoformat() and (not row['available_at'] or row['available_at']<=as_of)
def normalized(row):
    # Comparable dimensionless momentum; no raw units added to a posts count.
    d=row['dod_pct'];s=row['slope_7d'];v=row['value']
    return .6*math.tanh((d or 0)/50)+.4*math.tanh((s or 0)/max(abs(v)*.1,1))
def compute(con,as_of,run_id=None,catalysts_path=None,use_catalysts=False):
    from rolling_engine import pick_run,build_yesterday_complete_table,build_partial_table,load_t0_items,load_catalysts,catalyst_adj_for_sku,RollingRow
    migrate(con);cal,watch=config();run=pick_run(con,as_of,run_id);rid=run['run_id']
    complete,complete_day=build_yesterday_complete_table(con,rid,as_of);partial=build_partial_table(con,rid,as_of)
    metric_map={r['metric_key']:r for r in complete};obs=platform_rows(con,rid)
    anchors=[(date.fromisoformat(cal['anchors'][name])-date.fromisoformat(as_of)).days for name in cal['fulfillment_anchors']]
    positive=[n for n in anchors if n>=0];days=min(positive) if positive else 0
    bf=cal['anchors'].get('Black_Friday',cal['anchors'][cal['fulfillment_anchors'][0]])
    days_bf=(date.fromisoformat(bf)-date.fromisoformat(as_of)).days
    catalysts=load_catalysts(catalysts_path,as_of) if use_catalysts and catalysts_path else {'catalysts':[]}
    if catalysts.get('as_of_date')!=as_of:catalysts={'catalysts':[]}
    result=[]
    for baseline in load_t0_items(con):
        it=dict(baseline);sku=it['sku_cluster'];p=watch['profiles'][sku];primary=p['primary_metric'];m=metric_map.get(primary,{})
        # DoD requires adjacent calendar days; OLS uses actual calendar-day spacing.
        x_available=m.get('value') is not None
        x=.6*math.tanh((m.get('dod_pct') or 0)/50)+.4*math.tanh((m.get('slope_7d') or 0)/8) if x_available else 0
        valid=[r for r in obs if eligible(r,sku,as_of)]
        momentum={}
        for platform in ('TikTok','YouTube','GoogleTrends'):
            rs=[r for r in valid if r['platform']==platform and r['metric_key'] in ('content_velocity','video_view_velocity','search_velocity','hashtag_daily_growth') and (r['dod_pct'] is not None or r['slope_7d'] is not None)]
            if rs:momentum[platform]=sum(normalized(r) for r in rs)/len(rs)
        votes=([x] if x_available else [])+list(momentum.values())
        consensus=sum(v>.15 for v in votes)
        # Single-platform positive pulse discounted to 35%; negative X still risk-relevant.
        x_weight=.35 if x>0 and consensus<2 else 1.0
        cross=sum(momentum.values())/len(momentum) if momentum else 0
        demand=round(clip(2.5+1.4*x*x_weight+1.0*cross+(.4 if consensus>=2 else 0)),1)
        ads=[r for r in valid if r['platform'] in ('Meta','TikTok') and r['metric_key'] in ('active_ads','ad_scaling','content_velocity') and (r['dod_pct'] is not None or r['slope_7d'] is not None)]
        # Missing measured creative/ad conversion -> shrink design prior toward 2.5.
        ad=sum(normalized(r) for r in ads)/len(ads) if ads else 0
        content=round(clip(2.5+.7*(p['visual_hook']-.5)+.8*ad),1)
        # Lead-time scenario, not a warehouse claim. Nearest upcoming configured node.
        decay=max(0,(p['lead_days']+3-days)/(p['lead_days']+3))
        fulfill=round(clip(4.5+(.5 if p['us_ready_stock'] else -.4)-.5*p['bulky']-1.8*decay*(1-int(p['us_ready_stock']))-.5*p['size_risk']),1)
        reddit=[r['value'] for r in valid if r['platform']=='Reddit' and r['metric_key']=='complaint_share']
        complaint=sum(reddit)/len(reddit) if reddit else 0
        margin=round(clip(3+.8*p['bundle']+.6*p['repeat']-1.5*p['return_risk']-.7*p['size_risk']-.8*p['fragile_risk']-1.2*p['ip_risk']-.8*complaint),1)
        white=round(clip(3.5+1.2*p['differentiation']-2*p['brand_concentration']-1.2*p['ip_risk']-.4*max(0,ad)),1)
        c_adj,c_note=catalyst_adj_for_sku(sku,catalysts);c_adj=round(c_adj,1)
        total=round(demand+content+fulfill+margin+white+c_adj,1)
        note=(f'director_v1; X={x:.3f}, Xweight={x_weight:.2f}, daily_resonance={consensus}, fresh_cross={momentum}; '
              f'ads_n={len(ads)}; nearest_anchor_days={days}, lead={p["lead_days"]}, decay={decay:.3f}; '
              f'risk/warehouse/visual priors=analyst assumptions; Reddit_n={len(reddit)}; catalyst={c_note}; '
              'missing platforms are unknown, not zero; monthly context excluded')
        row=RollingRow(sku_cluster=sku,zh_name=zh_name(sku),t0_rank=it['rank_in_list'],t0_urgency=it['predicted_urgency'],t0_demand=it['predicted_demand'],t0_content=it['predicted_content'],t0_fulfill=it['predicted_fulfill'],t0_total=it['predicted_total'],rolling_urgency=0,rolling_demand=demand,rolling_content=content,rolling_fulfill=fulfill,catalyst_adj=c_adj,rolling_total=total,rolling_rank=0,rank_delta=0,demand_adj=round(demand-2.5,1),fulfill_adj=round(-1.8*decay,1),primary_metric=primary,dod_pct=m.get('dod_pct'),slope_7d=m.get('slope_7d'),consec_hot_days=m.get('consec_hot_days',0),action_note='仅轻测；缺多平台日频共振/真实毛利验证，禁止据代理热度重仓。',formula_note=note,predicted_action=it['predicted_action'],multi_platform_demand=demand,content_ad_leverage=content,fulfillment_sla=fulfill,margin_return_risk=margin,white_label_viability=white,live_total=total)
        result.append(row)
    result.sort(key=lambda r:(-r.live_total,r.t0_rank))
    for rank,row in enumerate(result,1):row.rolling_rank=rank;row.rank_delta=row.t0_rank-rank
    meta=dict(as_of_date=as_of,source_run_id=rid,complete_day=complete_day,black_friday=bf,days_to_bf=days_bf,days_to_tts=(date.fromisoformat(cal['anchors']['TTS_BFCM_window_start'])-date.fromisoformat(as_of)).days if 'TTS_BFCM_window_start' in cal['anchors'] else None,catalysts_path=str(catalysts_path or ''),catalysts_as_of=catalysts.get('as_of_date'),formula_version='director_v1',freeze_id=FREEZE_ID,run=dict(run),platform_signals=obs,nearest_anchor_days=days)
    return result,meta,complete,partial,rid

FORMULA_DOC='''## Director-Level Dual-Track（schema v5 / director_v1）
T0 `prediction_*` 与 freeze/T0 数字不变。T0 原四维 /20，Live 五维 /25，**不能把分差解释为同比提升**；只比较 Rank_Delta（T0_Rank − Rolling_Rank）。

每日五维各 clamp(0,5)，保留1位；Live_Rolling_Score = D+C+F+M+W+catalyst_adj。
- x = 0.6*tanh(X_DoD/50) + 0.4*tanh(X_slope_7d/8)。不足7日用已知连续序列并披露窗口；缺值贡献为中性但不是0帖量。
- 对 TT/YT/Google 近7日、已发布、非partial **日频**动量 z = .6*tanh(DoD/50)+.4*tanh(slope/max(.1*value,1))。c = 已有平台z均值。至少2个平台 z>0.15（含X）才共振。单平台正X脉冲系数a=.35，否则a=1。
- D=clamp(2.5+1.4*a*x+c+0.4*I(共振))。月度Newsroom仅背景，不充当11月日频共振。
- C=clamp(2.5+.7*(visual_hook-.5)+.8*ad_z)。ad_z为可用Meta/TT日频动量均值；缺广告数据回归保守中值+设计先验，非实测转化率。
- t=距配置中最近未来活动节点天数；h=max(0,(lead_days+3-t)/(lead_days+3))。
- F=clamp(4.5+(.5 if US现货验证 else -.4)-.5*bulky-1.8*h*(非US现货)-.5*size_risk)。当前无SKU美仓验证，均false；lead为情景假设。
- M=clamp(3+.8*bundle+.6*repeat-1.5*return_risk-.7*size_risk-.8*fragile-1.2*IP-.8*Reddit_complaint_share)。未知Reddit不等于无差评；风险、毛利、连带、仓储参数均**分析师先验**而非实测财务数据。
- W=clamp(3.5+1.2*differentiation-2*brand_concentration-1.2*IP-.4*max(0,ad_z))。
- catalyst_adj 可选，默认0。仅 `--with-catalysts` 且文件as_of等于报告日启用；每条权重限[-1,1]，合计限±2，非机器观测，不自动依赖其他窗口。
- 同分以T0原Rank稳定排序。Live总分如使用催化理论[-2,27]，五维自身各0–5。

### 采集与边界
`platform_signals` 保存run、真实测量窗口、来源URL、fetch timestamp、partial/proxy、NULL缺口；原始公开响应位于data/platform_raw。缺测不编量，不从搜索结果条数推断平台总量。TikTok月度背景保留真实期间，不能伪造11/03–11/06日频。Meta/IG/YT/Trends公开动态页未给时序就NULL。Reddit仅公开列表完整覆盖UTC日时使用词法差评样本；非退货率。

### 入口与日历
`python3 scripts/run_daily_pipeline.py --as-of YYYY-MM-DD --x-input data/x_YYYY-MM-DD.json`
原有X查询由本窗原生X connector取得，导出为数组：metric_key,signal_date,value,is_partial,source_note,as_of_ts。必须含昨日完整日及至少7日历史、今日partial。入口不读取token、不复制旧值；无X输入且无当日已有run则明确缺测。
配置：config/retail_calendar.json、config/watch_topics.json。黑五=2026-11-27。圣诞清仓/情人节只需更新节点、词池及SKU先验；引擎无需改日期。工作台仅只读。

### Walk-forward
11/08生成不可变Live T1；提前执行只dry-run；缺当日9个director_v1排名或完整X桶则不冻结。11/12、12/01执行backfill_actuals，只读真实完整UTC日桶，先回填actuals_daily/actuals_sku_window再计算**相对冻结前7日均值的日均增长**排名Spearman与rank MAE；不是销量/GMV。样本或窗口不足保持pending；并列用平均秩。
后续校准需积累多个独立窗口后再调参数；本版不在无actual时自动优化（避免泄漏/过拟合）。
'''
