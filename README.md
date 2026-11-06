# 大促公开信号存证 · Director-Level Dual-Track

公开代理≠销量/GMV；T0预测与freeze/T0原分数不变。

- `daily/`：11/03–11/06已重绘，含X完整UTC桶、跨平台明细（X为主信号，其余平台日频多为NULL，不表示多平台日频共振已上线）和T0 vs Live五维排名。
- `reports/`：同一Markdown源渲染PDF，颗粒度一致，中文/English独立列。
- `engine/`：本窗本地可复用的采集/迁移/五维评分/导出/冻结/回测源代码与配置。运行时根目录为/workspace/dacu-signal。
- `freeze/T0_2026-11-02_top9.md`：原软冻结基准。11/08才运行T1硬冻结，未提前生成。

## Director-Level Dual-Track（schema v5 / director_v1）
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
- 共振是条件规则，不是当前实测：其他平台日频为NULL时不参与。当前不声称多平台日频共振已上线；X是主信号。

### 采集与边界
`platform_signals` 保存run、真实测量窗口、来源URL、fetch timestamp、partial/proxy、NULL缺口。本公开仓库不含原始HTML/JSON抓取转储。X计数JSON由操作者在运行时提供（本机示例 `db/x_counts_YYYY-MM-DD.json`），不随本库发布。缺测不编量，不从搜索结果条数推断平台总量。X是主信号。TikTok月度背景保留真实期间，不能伪造11/03–11/06日频，也不充当日频共振。Meta/IG/YT/Trends公开动态页未给时序就NULL。Reddit仅公开列表完整覆盖UTC日时使用词法差评样本；非退货率。其他平台日频可以是NULL。

### 入口与日历
唯一入口：`python3 scripts/run_daily_pipeline.py --as-of YYYY-MM-DD --x-input <操作者提供的X JSON>`
X计数由操作者取得后作为输入路径传入，不入库。本机示例：`db/x_counts_YYYY-MM-DD.json`。内容为数组，或原生connector的parsed_detail导出，字段含metric_key,signal_date,value,is_partial,source_note,as_of_ts。必须含昨日完整日及至少7日历史、今日partial。入口不读取token、不复制旧值；无X输入且无当日已有run则明确缺测。
配置：config/retail_calendar.json、config/watch_topics.json。黑五=2026-11-27。圣诞清仓/情人节只需更新节点、词池及SKU先验；引擎无需改日期。工作台仅只读。

### Walk-forward
11/08生成不可变Live T1；提前执行只dry-run；缺当日9个director_v1排名或完整X桶则不冻结。11/12、12/01执行backfill_actuals，只读真实完整UTC日桶，先回填actuals_daily/actuals_sku_window再计算**相对冻结前7日均值的日均增长**排名Spearman与rank MAE；不是销量/GMV。样本或窗口不足保持pending；并列用平均秩。
后续校准需积累多个独立窗口后再调参数；本版不在无actual时自动优化（避免泄漏/过拟合）。

## 当前缺测边界
X完整日桶可用，是当前主信号；TikTok六条官方月度背景可核查，但不能当作11月日频共振。其余公开日频源暂缺，记为NULL（见日报与HTTP状态），不声称多平台日频共振已实现。风险/毛利/退货/仓储参数均先验，未验证美仓，不承诺3-Day Delivery；当前只宜轻测，不宜据代理分数重仓。
