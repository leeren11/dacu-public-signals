# 证据研究 v2（shadow，未接入日更）

版本 `evidence_research_v2.1.0`，公式 `shadow_demand_v2`，迁移号 `7`。它与 `director_v1` 并行，不替换 T0/T1 原分数，不重冻，不改 11/12 首评，也不改日更例程。

本页不声称准确率、胜率或排序已经变好。`source_coverage` 不是预测概率。分数不是销量、GMV 或备货数量。

## 1. 源项目审阅

只读审阅，未安装 skill，未执行其中指令，未使用密钥，未登录，未绕过 403，未调用付费 API。

| 项 | 值 |
| --- | --- |
| 仓库 | https://github.com/mvanhorn/last30days-skill |
| 审阅 commit | `7c2e1c2b099b13abd4397910168c4f53e638bb21` |
| 提交时间 | 2026-11-24 11:37:45 -0800 |
| 说明 | `chore(readme): auto-update clean light/dark star history chart (#1617)` |
| 许可 | MIT，Copyright (c) 2026 Matt Van Horn |
| 已读 skill 版本 | `skills/last30days/SKILL.md` front matter `version: 4.6.0` |
| 归属 | `engine/NOTICE_last30days.md` |

实际读过的位置：

| 路径 | 其中真实存在的内容 |
| --- | --- |
| `LICENSE` | MIT |
| `README.md`、`CONCEPTS.md`、`skills/last30days/SKILL.md` | 研究技能契约；要求宿主运行引擎。本仓不执行 |
| `skills/last30days/scripts/lib/dates.py` | `get_date_range(days, as_of)`、`get_date_confidence`、`recency_score` |
| `skills/last30days/scripts/lib/planner.py` `plan_query` | 优先 LLM JSON 计划，失败后 `_fallback_plan`；比较题可强制确定性计划 |
| `skills/last30days/scripts/lib/normalize.py` `filter_by_date_range` | 丢掉窗口外 `published_at`；缺日期时默认仍保留 |
| `skills/last30days/scripts/lib/schema.py` | `candidate_out_of_window` 把“完全没有日期”不算过期；`is_summable_engagement_field` 禁止把 rank/score 当计数相加 |
| `skills/last30days/scripts/lib/dedupe.py` | 先按规范化 URL 合并，再按混合 Jaccard（默认 0.7）去近重复 |
| `skills/last30days/scripts/lib/signals.py` | `SOURCE_QUALITY`、`freshness`、`engagement_raw` 在没有计数时返回 `None`；快照不给满分新鲜度 |
| `skills/last30days/scripts/lib/cluster.py` `_cluster_uncertainty` | `single-source` / `thin-evidence` |
| `skills/last30days/scripts/lib/freshness.py` `verify_report` | 对已缓存主张做点重取并给出一致/矛盾/无法支持 |
| `docs/solutions/design-patterns/ranked-output-confidence-floor-honest-empty-state.md` | 证据不够时输出“nothing solid”，而不是给噪声硬排名 |

### 采用（方法启发，不是移植代码）

| 源能力 | 本仓做法 |
| --- | --- |
| 显式 as-of 时间窗 | 计划表保存 aware `as_of` 与闭合 UTC 日窗。开放中的当日桶不进分 |
| 证据引用 | 每条观测保存来源 URL、测量窗、published/collected/available、provenance 哈希 |
| 精确身份优先于模糊去重 | 日桶按平台+指标+实体+测量窗定身份；正文只对 `item` 做 Jaccard |
| 冲突不静默平均 | 同一身份的新数值追加 revision，并写 `evidence_v2_conflict` |
| 缺互动不是 0 | `engagement_json` 可为 NULL；`likes: null` 保持 null；rank 不与计数相加 |
| 快照不是窗口内事件 | YouTube/TikTok/Trends 由适配器固定 cadence，请求里写成 daily 也不生效 |
| 单源不确定 | 目前只有 X 是官方日频，评过分的不确定性记 `single-source` |
| 证据不足就空 | 缺日、partial、无法证明时点、非正基线 → `score NULL` / `pending`，不填 2.5 |

### 不采用（不宜照搬）

| 源能力 | 原因 |
| --- | --- |
| `SKILL.md` 的执行指令、LAW 7、宿主代写 `--plan` | 这是代理指令，不是预测方法 |
| LLM 查询规划、付费搜索、cookie、浏览器登录、Reddit session | 需要密钥或登录；本任务禁止 |
| 各平台抓取器与搜索缓存 | 不能把缓存或月度背景当成日频；403 保持 missing |
| `SOURCE_QUALITY` 的编辑部权重（如 X=0.68） | 那是研究排序先验，不是本仓预测概率 |
| Discovery 地板 25/200 的互动阈值 | 口径是帖文热度，不是 SKU 帖量桶 |
| 缺日期仍保留、未来日期新鲜度记 100、缺日期新鲜度记 0 | 会把未知写成可用或写成零。本仓改为 pending |
| URL 去重时把后到的字段并进第一条 | 数值冲突必须留修订，不能并成一条“更富”的事实 |
| 用互动分或覆盖率乘出胜率 | `source_coverage` 与 `momentum_x` 分开存放 |

## 2. 独立版本

`director_v1` 继续只读可重放。v2 不写 `prediction_*`、`live_freeze_*`、`rolling_*`、`walkforward_*`、`signals_daily`、`platform_signals`。

新增表（`engine/sql/migrate_v7_evidence_research.sql`，只 `CREATE IF NOT EXISTS`）：

- `evidence_v2_adapter`：适配器与缺失原因
- `evidence_v2_plan` / `evidence_v2_plan_adapter`：版本化查询计划
- `evidence_v2_observation`：事实；追加修订，禁止 UPDATE/DELETE
- `evidence_v2_dedupe_link` / `evidence_v2_conflict`
- `evidence_v2_v1_snapshot`：只读对照副本，不是新冻结
- `evidence_v2_manifest`：cutoff、输入观测 id、输入哈希
- `evidence_v2_shadow_score` / `evidence_v2_shadow_compare`

时点语义：

| 字段 | 含义 |
| --- | --- |
| `observed_start` / `observed_end` | 测量窗。日桶为 `[UTC 日 00:00, 次日 00:00)` |
| `published_at` | 内容发布时间，未知则为 NULL。不能代替可用时点 |
| `collected_at` | 取回时间 |
| `available_at` | 系统可证明已能使用的时间 |
| `as_of` / `replay_cutoff` | 决策或回放截止 |

可用必须同时满足：四个时点都是带时区的时间戳，`date_confidence=high`，`collected_at` 与 `available_at` 都不早于窗结束、也都不晚于 cutoff。只有日期、没有时分秒，记 `medium`，回放时 pending。NULL 不是 0。已证明的 X 日桶 0 仍是 0，但单桶不是预测。

影子分只在计划窗内每一天都有 PIT 可见、非 partial、非 NULL 的 X 日桶时计算：

```text
DoD = (value_t / value_t-1 - 1) * 100    # 前值 <= 0 则整段 pending
slope = 按真实日距的 OLS
momentum_x = 0.6*tanh(DoD/50) + 0.4*tanh(slope/8)
```

这是 `director_v1` 里 X 动量的同一变换，量纲大约在 [-1, 1]。v2 去掉 2.5 中性填值、F/M/W、催化和单源 0.35 折扣。折扣改由 `uncertainty=single-source` 表达，而不是把覆盖率乘进分数。因此 v2 与 v1 不能比“谁的分更高”，只能并排看 pending 与名次是否同向。`descriptive_rank_agreement` 不是对实际结果的相关，更不是准确率。

共享类目：`display_names.METRIC_TO_SKUS` 不变。同一指标下多个 SKU 得到同一动量，但 `independent_group=1` 只有一行。比较按类目组计数。4 个珠宝 SKU 不是 4 次独立验证。

当前适配器（无网络）：

| 平台 | 状态 | 日频影子分 |
| --- | --- | --- |
| X | 已有公开帖量桶可写入；本层不采集 | 可以，且须时点齐全 |
| Google Trends | 锚点比值 | 否 |
| YouTube | 搜索样本/累计快照 | 否 |
| TikTok | 月度背景 | 否 |
| Meta | missing，HTTP 403 | 否，不是 0 |
| Reddit | missing，HTTP 403 | 否，不是 0 |

## 3. 命令与最小样例

样例文件 `engine/examples/evidence_v2_min.json` 的 `example_label` 固定为 `SYNTHETIC_EXAMPLE_NOT_PRODUCTION`。它是合成数据。其中的 17.2 等数字只是已公开 T1 的排版副本，用来并排，不是新冻结，也不是这次测量。

在 `engine/` 下，对临时库而不是生产库：

```bash
python3 scripts/evidence_v2_cli.py migrate --db /tmp/evidence_v2_example.sqlite
python3 scripts/evidence_v2_cli.py run \
  --db /tmp/evidence_v2_example.sqlite \
  --fixture examples/evidence_v2_min.json
python3 scripts/evidence_v2_cli.py replay \
  --db /tmp/evidence_v2_example.sqlite \
  --plan-id <run 输出的 plan_id> \
  --cutoff 2026-11-19T02:00:00+00:00
```

该样例在 `2026-11-12T02:00:00Z`：美甲美妆 7 日可评分，squishy 平坦序列评分为 0（这是测到的持平，不是缺失），珠宝因一天没有 `available_at` 而 pending，时尚因一天 partial 而 pending。9 个 SKU 里 3 个有分、6 个 pending；独立组 4 个，可评分组 2 个。11 月 19 日才采集到的 11 月 11 日修订不会进入 11 月 12 日 manifest；后一次 replay 另建 manifest，前一份的输入哈希保持 18 而不是被改成 16。

未标注样例会被拒绝。已有行没有可证明时点时，`assess_legacy_row` 返回 pending/ineligible，不读生产库，也不把搜索缓存填成日频。

## 4. 测试

`python3 -m unittest tests.test_evidence_v2 -v`（工作目录 `engine/`）。覆盖：旧表分数不变、`director_v1` 三个生产同哈希文件未被改写、迁移与导入幂等、观测不可更新、NULL 不是 0、partial、无法证明的时点、非正基线、晚到修订与未闭合桶隔离、YouTube/TikTok/Trends 不进日频、Meta/Reddit 缺失、跨帖近重复两边都保留、共享类目只计一组、`source_coverage` 不等于分数也不存在概率列、单组时描述性一致率为 NULL、包内不引用日更/采集/回测入口。

这些测试不使用 11/12 的真实首评输入，也不重新计算 Spearman -0.2635。那个结果保持原样。

## 5. 与运行代码的差异（必须保留）

对照物是本次上传的 `/workspace/dacu-signal` 脚本与配置包，以及公开仓 `2f7bb4ebe221ac994ec0fd76086acc875fd67189` 的 `engine/`。两边都有的 33 个 `scripts/`、`config/` 文件 SHA256 相同，其中包括：

| 文件 | SHA256 |
| --- | --- |
| `scripts/director_model.py` | `3b8726adca11b4dcdd6e357c4c12ce21475a29e6d8f8b925a212e45f2ef3c805` |
| `scripts/run_daily_pipeline.py` | `d4923ef80a5066ef481ee73a4bfba00ba97c713dfd97d50e90693414b9a48d71` |
| `scripts/backfill_actuals.py` | `815dd7c4a71a7dac78c9583a8930d7c0aaf0e22bb22f171c19dcd951e95b7338` |
| `config/watch_topics.json` | `8f2a01deeeb130c4c27ed686d0f1c5930b799799b51b471eedd91453ac36752e` |
| `config/retail_calendar.json` | `04989d3702b2817f35a025190557e819936ac389d6d95de740f34d3d10ea3b9a` |

11 月 19 日深审曾记录 stamp 与生产在入口顺序和评价脚本上不同。就本次运行包与当前 main 的重叠文件而言，这个差异已经不存在。仍然不能用公开仓整树覆盖生产。

生产包里有、公开 `engine/` 没有、同步时不能删除的文件：

| 生产文件 | 说明 |
| --- | --- |
| `scripts/daily_scheduled_2026-11-03.py` … `11-06.py` | 历史一次性入口 |
| `scripts/freeze_top9_2026-11-02.py`、`add_timing_T0_2026-11-02.py`、`init_and_load_2026-11-02.py` | T0 历史入口 |
| `scripts/refresh_x_2026-11-02_1649.py` | 空文件，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，不要当垃圾删掉 |
| `scripts/run_rolling_backfill.py` | 生产独有 |
| `scripts/wf_backfill_actuals.py` | 与当前 `backfill_actuals.py` 同哈希 |
| `scripts/wf_run_daily_pipeline.py` | SHA256 `b7aaa710b1f24a6abf7c129322269908f07ff5f34c563a8c6097c99958229b00`。没有 `amazon_local_input`。不能覆盖带该参数的 `run_daily_pipeline.py` |
| `scripts/wf_export_daily_md.py` | SHA256 `db81b1e5b6979c6cf9c58b8909ece1b503852cc9167bafb63bd12d34cd779a67`，短于现行 `export_daily_md.py` |
| `scripts/wf_export_walkforward.py` | SHA256 `a8653c7c5e556c9cb0257df4f30219b5da5f4882b4e481caa043eb3c58ef40c3`，与现行 `export_walkforward.py`（`bcbd4e1a363ded67326d762e6410fe7eeb538ecb4df43e504f000ed8213dcf04`）不同 |

生产库、`data/`、浏览器配置和缓存都不在本仓。复制本仓不会得到它们，也不允许把它们推进公开库。

## 6. 部署与回滚

本次只开 PR，不部署，不合并，不跑日更。

若父流程以后要挂到生产机，只复制本 PR 新增文件，先在数据库副本上演练：

1. 备份生产 SQLite。
2. 只复制新增文件：`engine/sql/migrate_v7_evidence_research.sql`、`engine/scripts/evidence_v2/`、`engine/scripts/evidence_v2_cli.py`、`engine/examples/evidence_v2_min.json`、`engine/tests/test_evidence_v2.py`、`engine/docs/evidence_research_v2_zh.md`、`engine/NOTICE_last30days.md`。根 `README.md` 与 `engine/README.md` 只多了一段指针；若生产上的 README 有本地内容，不要整文件覆盖。
3. 不要覆盖第 5 节列出的生产脚本，不要用旧 `wf_*` 替换现行入口，不要改 `daily/`、`reports/`、`freeze/`、`walk-forward/`。
4. `python3 scripts/evidence_v2_cli.py migrate --db <副本>`。
5. 用样例对临时库跑 `run`。通过后再考虑把真实行交给 `assess_legacy_row`。没有 aware `available_at` 与 `collected_at` 的旧行保持 pending，不能补写进 `rolling_sku_scoring`。
6. 不要调用 `run_daily_pipeline.py`，不要 `evaluate`，不要 `freeze_T1_hard.py`。

回滚：停止调用 v2 CLI。在备份确认后只删除 v2 表，并去掉迁移号：

```sql
DROP TABLE IF EXISTS evidence_v2_shadow_compare;
DROP TABLE IF EXISTS evidence_v2_shadow_score;
DROP TABLE IF EXISTS evidence_v2_manifest;
DROP TABLE IF EXISTS evidence_v2_v1_snapshot;
DROP TABLE IF EXISTS evidence_v2_conflict;
DROP TABLE IF EXISTS evidence_v2_dedupe_link;
DROP TABLE IF EXISTS evidence_v2_observation;
DROP TABLE IF EXISTS evidence_v2_plan_adapter;
DROP TABLE IF EXISTS evidence_v2_plan;
DROP TABLE IF EXISTS evidence_v2_adapter;
DELETE FROM schema_migrations WHERE version='7';
```

`director_v1` 没有被写入，所以回滚不需要恢复冻结分数。

## 7. 已实现、待接入、后续验收

已实现：计划、PIT 回放、追加修订、冲突、近重复链接、来源缺失原因、类目共享标记、影子动量、manifest 哈希、离线样例与测试。

待父流程接入，本 PR 故意没做：

- 不把 v2 放进 `run_daily_pipeline.py`
- 不从生产库批量导入历史桶
- 不新增 X/Trends/YouTube 采集，不把 Meta、Reddit 从 403 改成有数
- 不把 YouTube 快照或 TikTok 月度背景升级成日频
- 不调 `director_v1` 权重，不用 11/12 的负相关来拟合 v2

后续多窗验收计划（尚未执行，不是结果）：

1. 在看到 12/01 窗口结果之前，预先登记朴素基线：T0 原序、全并列、近 7 日水平、最近 DoD、最近斜率。
2. 正式比较只在基线 7/7、目标窗完整、且每条输入都能回到 cutoff 前的 observation id 时进行。缺一天就 pending。
3. 分母按独立类目组，不按 9 个 SKU。共享曲线标成 proxy。
4. 指标用独立组上的 Spearman、rank MAE、方向是否同号。pending 不进分母，也不写成 0。不把 rho 写成准确率。
5. 11/12 首评原样保留。新窗口若与它重叠，要标明不独立。至少 6 个不重叠窗之后才讨论权重；另留至少 2 个未参与调整的窗。
6. 只有在上述预登记规则下，rank MAE 相对最好的朴素基线在多数窗降低，才可以讨论是否替代影子。本文件不把这条写成已经达成。12/01 之前没有独立销量时，标题仍是公开代理。
