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

## 运行与验证
- 唯一入口：`python3 scripts/run_daily_pipeline.py --as-of YYYY-MM-DD --x-input <操作者提供的X JSON>`
- `python3 -m unittest discover -s tests -v`
- `python3 scripts/run_daily_pipeline.py --as-of 2026-11-06`（本机若已有当日 `db/x_counts_2026-11-06.json` 可复用当日run；该文件不在本库）
- `python3 scripts/freeze_T1_hard.py --dry-run`（T1硬冻结辅助；日更入口仍是 `run_daily_pipeline.py`）
- 输出MD：`/workspace/dacu-public-signals-stamp/daily/YYYY-MM-DD.md`
- 输出PDF：`reports/dacu_daily_YYYY-MM-DD.pdf`，并复制至stamp/reports/便于同次发布。
- `external_catalysts.json`非依赖，默认不启用；无需其他窗口写入。
- 本机SQLite与T0核验快照（如 `db/pre_director_v5.sqlite`、`data/pre_director_t0_snapshot.json`）以及原始网页抓取**不要推公开库**。
- 本地脚本不push、不更改挂载Routine；由父agent统一发布和更新9:30计划。

## 采集能力事实（2026-11-06 Asia/Shanghai）
已取得：X已有原生完整桶；TikTok官方Newsroom六条8→9月背景。
未取得：TT CC日频/互动率；Meta在投广告计数；IG趋势；YouTube日频观看增长；Google Trends购买词日频；Reddit完整日口碑。
HTTP成功不等于有时间序列：CreativeCenter和IG为动态/登录页面；YouTube支持公开结果中的当日lifetime-view样本快照（如能解析），不是完整日桶；Meta/Reddit HTTP403，Trends HTTP429。NULL明确留档。
故当前Live是“X动量+风险先验的保守五维模型”，**不声称已实现全平台实测共振**；有多源真实日频输入时自动参与，不把旧月度数伪装为每日增长。
