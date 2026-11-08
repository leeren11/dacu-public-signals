# 大促公开信号 · Director-Level Rolling Engine

本窗「黎治工作」独立闭环；工作台只读。公开代理，不编GMV。

## Director-Level Dual-Track（schema v5 / director_v1）
T0 `prediction_*` 与 freeze/T0 数字不变。T0 原四维 /20，Live 五维 /25，**不能把分差解释为同比提升**；只比较 Rank_Delta（T0_Rank − Rolling_Rank）。

每日五维各 clamp(0,5)，保留1位；Live_Rolling_Score = D+C+F+M+W+catalyst_adj。
- x = 0.6*tanh(X_DoD/50) + 0.4*tanh(X_slope_7d/8)。不足7日用已知连续序列并披露窗口；缺值贡献为中性但不是0帖量。
- 对 TT/YT/Google 近7日、已发布、非partial **日频**动量 z = .6*tanh(DoD/50)+.4*tanh(slope/max(.1*value,1))。c = 已有平台z均值。至少2个平台 z>0.15（含X）才共振。单平台正X脉冲系数a=.35，否则a=1。
- D=clamp(2.5+1.4*a*x+c+0.4*I(共振))。月度Newsroom仅背景，不充当11月日频共振。
- C=clamp(2.5+.7*(visual_hook-.5)+.8*ad_z)。ad_z为可用Meta/TT日频动量均值；缺广告数据回归保守中值+设计先验，非实测转化率。
- t=距配置中最近未来活动节点天数；h=max(0,(lead_days+3-t)/(lead_days+3))。
- F 分档：lead<=7 或 us_ready_stock → 现货/轻小件，t≥3 时 decay_eff=0，F 稳定在 3.8–4.2；lead>=12 长链路用 2.0*h 强化衰减；中间带半强度。us_ready_stock 当前全 false（无美仓核验），lead 为情景假设。
- M=clamp(3+.8*bundle+.6*repeat-1.5*return_risk-.7*size_risk-.8*fragile-1.2*IP-.8*Reddit_complaint_share)。未知Reddit不等于无差评；风险、毛利、连带、仓储参数均**分析师先验**而非实测财务数据。
- W=clamp(3.5+1.2*differentiation-2*brand_concentration-1.2*IP-.4*max(0,ad_z))。
- catalyst_adj 可选；`--with-catalysts` 启用。报告日匹配文件 as_of 时正常注入；历史重绘允许权重 overlay（不伪造跨平台日桶）。
- 同分以T0原Rank稳定排序。Live总分如使用催化理论[-2,27]，五维自身各0–5。

### 采集与边界
`platform_signals` 保存run、真实测量窗口、来源URL、fetch timestamp、partial/proxy、NULL缺口。采集层：Playwright 持久化 Chromium（data/browser_profile）+ curl_cffi chrome124 + 拟人抖动；禁止裸 requests 抓目标 HTML。缓存 data/platform_cache；原始证据 data/platform_raw（均不入库）。缺测不编量。TikTok Newsroom 月度仅背景。Meta/IG/YT/Trends 失败则 NULL。Reddit 公开 JSON（合规 UA）词法差评样本；非退货率。

### 入口与日历
`python3 scripts/run_daily_pipeline.py --as-of YYYY-MM-DD --x-input data/x_YYYY-MM-DD.json`
原有X查询由本窗原生X connector取得，导出为数组：metric_key,signal_date,value,is_partial,source_note,as_of_ts。必须含昨日完整日及至少7日历史、今日partial。入口不读取token、不复制旧值；无X输入且无当日已有run则明确缺测。
配置：config/retail_calendar.json、config/watch_topics.json。黑五=2026-11-27。圣诞清仓/情人节只需更新节点、词池及SKU先验；引擎无需改日期。工作台仅只读。

### Walk-forward
11/08生成不可变Live T1；提前执行只dry-run；缺当日9个director_v1排名或完整X桶则不冻结。11/12、12/01先执行 `backfill_actuals.evaluate`，再导出日更。evaluate 只读真实完整 UTC 日桶，先回填 actuals，再计算**相对冻结前 7 日日均的增长**以及 Spearman / rank MAE。人类读 `walk-forward/walkforward_YYYY-MM-DD.md`：冻结时的秩/动作/分数、基线对评估窗的逐日爬坡、已入库的其他平台行、以及测款/预热/观望是否还站得住。JSON 保存同一内容和 `climb.series`。公开帖量代理，不是销量或 GMV，不写准确率。窗口不齐就 pending。建议提交说明：`walkforward: YYYY-MM-DD`。
后续校准需积累多个独立窗口后再调参数；本版不在无actual时自动优化（避免泄漏/过拟合）。

## Amazon BSR 证据层（独立，未接入 Live）

US Keepa 名次、价格和评论计数的证据表，不改 T0/T1，也不改 11/12 与 12/01 的回测权重。操作命令、空池 `needs_input`、以及加权重之前要满足的条件见 `docs/amazon_bsr_zh.md`。默认不发实时请求；没有 `KEEPA_API_KEY` 时状态是不可用，不是流水线失败。本机 SQLite 备份不是异地备份。

## 运行与验证
- `python3 -m unittest discover -s tests -v`
- `python3 scripts/run_daily_pipeline.py --as-of 2026-11-06 --with-catalysts`（已有X数据可复用当日run；拟人采集较慢）
- `python3 scripts/freeze_T1_hard.py --dry-run`
- 输出MD：`/workspace/dacu-public-signals-stamp/daily/YYYY-MM-DD.md`
- 输出PDF：`reports/dacu_daily_YYYY-MM-DD.pdf`，并复制至stamp/reports/便于同次发布。
- 评估日额外输出：`/workspace/dacu-public-signals-stamp/walk-forward/walkforward_YYYY-MM-DD.md` 与 `.json`（逐日爬坡 + 冻结对照），并写一份到运行时 `reports/`。流水线在导出日更之前执行 evaluate。本地脚本仍不 push。
- 不运行旧daily_scheduled_2026-*作为未来入口；它们仅历史迁移归档，包含静态T0复制逻辑。
- `external_catalysts.json`非依赖，默认不启用；无需其他窗口写入。
- SQLite迁移前快照：db/pre_director_v5.sqlite；T0核验：data/pre_director_t0_snapshot.json。备份/原始网页**不要推公开库**。
- 本地脚本不push、不更改挂载Routine；由父agent统一发布和更新9:30计划。

## 采集能力事实（见 reports/ANTIBOT_V1_HANDOFF.md 最新实测）
采集已切换拟人浏览器架构。成功源写入有数值；403/429/空壳仍 NULL+原因，不编量。
Live 仍可能以 X + 稀疏跨平台 + 分析师先验为主；**不声称全平台日频共振**，除非 Cross-Platform Summary「有数值」列对应该平台真正亮起。
