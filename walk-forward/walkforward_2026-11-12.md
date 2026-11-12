# Walk-forward 回看 · 2026-11-12

- 评估日：2026-11-12。评估窗：2026-11-11 .. 2026-11-11（完整 UTC 日，不含评估日当天）。
- 读法：先看一页结论和运营结论，再下翻到每个 SKU 的预测情况、数据爬坡、公开实际对照。
- 相对增长 = 评估窗日均帖量 / 冻结前 7 个完整日的日均帖量 − 1。指数 1.00 表示等于该基线。
- 生成时间（Asia/Shanghai）：2026-11-12T09:45:27+08:00

## 一页结论

| freeze_id | 冻结日 | n | pending | Spearman | rank MAE |
| --- | --- | --- | --- | --- | --- |
| T0_2026-11-02_top9 | 2026-11-02 | 0 | 9 | — | — |
| T1_2026-11-08_top9 | 2026-11-08 | 9 | 0 | -0.2635 | 3.667 |

这个评估窗只有 1 日。同向或走弱只记方向，不升格成站得住或伪热。

共用曲线：珠宝礼赠（`jewelry_gift_posts`）由 镀金中粗圈耳环、叠戴细链套装、友谊串珠手链、现货欧泊/字母吊坠 共用；美甲美妆（`nail_makeup_gift_posts`）由 节日甲片、唇膏小礼盒 共用；时尚礼赠（`fashion_gift_posts`）由 法兰绒家庭 PJs、燕麦色宽松粗针毛衣 共用。这些 SKU 的爬坡不是各自的订单。

| 中文名 | 冻结 | 预测秩 | 动作 | 冻结分 | 形态 | 相对增长 | 实际秩 | rank_error | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 镀金中粗圈耳环 | T0_2026-11-02_top9 | 1 | 测款 | 18.0/20 | 日桶未齐 | — | — | — | pending |
| 叠戴细链套装 | T0_2026-11-02_top9 | 2 | 测款+预热 | 18.0/20 | 日桶未齐 | — | — | — | pending |
| 友谊串珠手链 | T0_2026-11-02_top9 | 3 | 轻测 | 18.0/20 | 日桶未齐 | — | — | — | pending |
| 现货欧泊/字母吊坠 | T0_2026-11-02_top9 | 4 | 测款 | 18.0/20 | 日桶未齐 | — | — | — | pending |
| 节日甲片 | T0_2026-11-02_top9 | 5 | 测款 | 18.0/20 | 日桶未齐 | — | — | — | pending |
| 唇膏小礼盒 | T0_2026-11-02_top9 | 6 | 测款+预热 | 18.0/20 | 日桶未齐 | — | — | — | pending |
| squishy 多件装 | T0_2026-11-02_top9 | 7 | 轻测 | 16.0/20 | 日桶未齐 | — | — | — | pending |
| 法兰绒家庭 PJs | T0_2026-11-02_top9 | 8 | 轻测+内容 | 15.0/20 | 日桶未齐 | — | — | — | pending |
| 燕麦色宽松粗针毛衣 | T0_2026-11-02_top9 | 9 | 内容预热 | 15.0/20 | 日桶未齐 | — | — | — | pending |
| 节日甲片 | T1_2026-11-08_top9 | 1 | 测款 | 17.2/25 | 爬坡 | +18.8% | 1.50 | 0.50 | observed |
| 现货欧泊/字母吊坠 | T1_2026-11-08_top9 | 2 | 测款 | 16.2/25 | 走平 | -3.2% | 7.50 | 5.50 | observed |
| 叠戴细链套装 | T1_2026-11-08_top9 | 3 | 测款+预热 | 16.0/25 | 走平 | -3.2% | 7.50 | 4.50 | observed |
| 友谊串珠手链 | T1_2026-11-08_top9 | 4 | 轻测 | 16.0/25 | 走平 | -3.2% | 7.50 | 3.50 | observed |
| 镀金中粗圈耳环 | T1_2026-11-08_top9 | 5 | 测款 | 15.7/25 | 走平 | -3.2% | 7.50 | 2.50 | observed |
| 唇膏小礼盒 | T1_2026-11-08_top9 | 6 | 测款+预热 | 15.4/25 | 爬坡 | +18.8% | 1.50 | 4.50 | observed |
| squishy 多件装 | T1_2026-11-08_top9 | 7 | 轻测 | 13.4/25 | 走平 | -0.6% | 5.00 | 2.00 | observed |
| 法兰绒家庭 PJs | T1_2026-11-08_top9 | 8 | 轻测+内容 | 12.6/25 | 走平 | +2.7% | 3.50 | 4.50 | observed |
| 燕麦色宽松粗针毛衣 | T1_2026-11-08_top9 | 9 | 内容预热 | 11.5/25 | 走平 | +2.7% | 3.50 | 5.50 | observed |

## 运营结论

### 初步同向

- 节日甲片 在 1 个评估日上，公开主指标相对冻结前 7 日日均 +18.8%，形态爬坡。与冻结动作「测款」同向，只记初步迹象。窗口太短，不能说这条测款或预热已经站得住。 主指标与 唇膏小礼盒 共用，这个判断不是该 SKU 的独立订单证据。
- 唇膏小礼盒 在 1 个评估日上，公开主指标相对冻结前 7 日日均 +18.8%，形态爬坡。与冻结动作「测款+预热」同向，只记初步迹象。窗口太短，不能说这条测款或预热已经站得住。 主指标与 节日甲片 共用，这个判断不是该 SKU 的独立订单证据。

### 短窗未爬坡

- 现货欧泊/字母吊坠 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 2 的「测款」升格成伪热结论。 主指标与 叠戴细链套装、友谊串珠手链、镀金中粗圈耳环 共用，这个判断不是该 SKU 的独立订单证据。
- 叠戴细链套装 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 3 的「测款+预热」升格成伪热结论。 主指标与 现货欧泊/字母吊坠、友谊串珠手链、镀金中粗圈耳环 共用，这个判断不是该 SKU 的独立订单证据。
- 友谊串珠手链 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 4 的「轻测」升格成伪热结论。 主指标与 现货欧泊/字母吊坠、叠戴细链套装、镀金中粗圈耳环 共用，这个判断不是该 SKU 的独立订单证据。
- 镀金中粗圈耳环 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 5 的「测款」升格成伪热结论。 主指标与 现货欧泊/字母吊坠、叠戴细链套装、友谊串珠手链 共用，这个判断不是该 SKU 的独立订单证据。
- squishy 多件装 只有 1 个评估日，公开主指标 -0.6%，形态走平。短窗走弱或走平只记录方向，不把预测秩 7 的「轻测」升格成伪热结论。
- 法兰绒家庭 PJs 只有 1 个评估日，公开主指标 +2.7%，形态走平。短窗走弱或走平只记录方向，不把预测秩 8 的「轻测+内容」升格成伪热结论。 主指标与 燕麦色宽松粗针毛衣 共用，这个判断不是该 SKU 的独立订单证据。
- 燕麦色宽松粗针毛衣 只有 1 个评估日，公开主指标 +2.7%，形态走平。短窗走弱或走平只记录方向，不把预测秩 9 的「内容预热」升格成伪热结论。 主指标与 法兰绒家庭 PJs 共用，这个判断不是该 SKU 的独立订单证据。

### 未能对照（pending）

- 镀金中粗圈耳环 的冻结动作是「测款」（预测秩 1）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 叠戴细链套装 的冻结动作是「测款+预热」（预测秩 2）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 友谊串珠手链 的冻结动作是「轻测」（预测秩 3）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 现货欧泊/字母吊坠 的冻结动作是「测款」（预测秩 4）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 节日甲片 的冻结动作是「测款」（预测秩 5）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 唇膏小礼盒 的冻结动作是「测款+预热」（预测秩 6）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- squishy 多件装 的冻结动作是「轻测」（预测秩 7）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 法兰绒家庭 PJs 的冻结动作是「轻测+内容」（预测秩 8）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。
- 燕麦色宽松粗针毛衣 的冻结动作是「内容预热」（预测秩 9）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

### 履约拖累假说

- squishy 多件装：lead_days=12，冻结时按长链路情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是日桶未齐。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。
- 法兰绒家庭 PJs：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是日桶未齐。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。
- 燕麦色宽松粗针毛衣：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是日桶未齐。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。
- squishy 多件装：lead_days=12，冻结时按长链路情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是走平。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。
- 法兰绒家庭 PJs：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是走平。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。
- 燕麦色宽松粗针毛衣：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是走平。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。

### 边界

- 对照的是 X 完整 UTC 帖量，以及评估窗里真实写进 platform_signals 的其他公开行。
- 本次数源没有 GMV、订单、退货或美仓实测。
- 同一主指标上的多个 SKU 共用一条曲线，排名会并列，不能当成各自的订单。
- Spearman 与 rank MAE 只在增长率可算的 SKU 子集上计算；有效样本少于 3 时 Spearman 为空。
- 形态阈值 ±10% 只用来描述帖量路径。评估窗少于 5 日时只记方向。
- action_hit、timing_hit、checkpoint_actuals 本导出不写入；到点的检查点保持 pending。
- 配置中的 Black_Friday = 2026-11-27。本导出不改这个锚点，也不改 T0/T1 冻结原文。

## T0_2026-11-02_top9

- 冻结日：2026-11-02；状态：soft
- 标签：今日优先 Top9 软冻结基线（可回测）
- 冻结备注：用户要求立即保留今日 Top9 预测作可回测基线；正式硬冻结仍可在 11/8–11/9 另开 hard；公开代理、不编 GMV
- 基线窗：2026-10-26 .. 2026-11-01（冻结日当天不计入）
- 有效样本 n=0，pending=9，Spearman=—，rank MAE=—
- 汇总说明：Public proxy only; rank MAE recomputed on common valid subset; category duplicates not independent. No model calibration until multiple independent windows.

### 镀金中粗圈耳环

English SKU：`gold medium/chunky hoop earrings`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 1 |
| 冻结动作 predicted_action | 测款 |
| 对照用动作 | 测款 |
| urgency | 4.0 |
| demand | 5.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 18.0/20 |
| price_band | $12-28 |

- 发酵窗：2026-11-08 .. 2026-11-15
- 高峰窗：2026-11-11 .. 2026-11-30
- verify_by：2026-12-01
- 冻结时的窗假设：开窗前后种草抬升；TTS 珠宝代理随 BFCM 进入成交峰（预测，非事实）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-09 | 预热/报名启动核 | 已到 | 内容预热或报名讨论相对 11/02 基线启动（非爆发亦可） | pending，本导出不写 hit |
| 2026-11-15 | TTS 窗内珠宝代理 | 未到期 | TTS 开窗后珠宝∩gift 公开代理抬升 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | BFCM 窗后公开代理回看是否完成「测款→可见抬升」路径 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 250, 304, 282, 305, 260, 237 → 258

主指标与 叠戴细链套装、友谊串珠手链、现货欧泊/字母吊坠 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 250 | — | — | observed |
| 2026-10-28 | 基线 | 304 | — | +21.6 | observed |
| 2026-10-29 | 基线 | 282 | — | -7.2 | observed |
| 2026-10-30 | 基线 | 305 | — | +8.2 | observed |
| 2026-10-31 | 基线 | 260 | — | -14.8 | observed |
| 2026-11-01 | 基线 | 237 | — | -8.8 | observed |
| 2026-11-11 | 评估窗 | 258 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 13 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 28308 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

镀金中粗圈耳环 的冻结动作是「测款」（预测秩 1）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 叠戴细链套装

English SKU：`layering/paperclip necklace set`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 2 |
| 冻结动作 predicted_action | 测款+预热 |
| 对照用动作 | 测款+预热 |
| urgency | 4.0 |
| demand | 5.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 18.0/20 |
| price_band | $15-35 |

- 发酵窗：2026-11-05 .. 2026-11-12
- 高峰窗：2026-11-11 .. 2026-11-30
- verify_by：2026-12-01
- 冻结时的窗假设：叠戴细链发酵略早于圈耳环，预热窗更长；峰对齐 BFCM（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-08 | 早发酵核 | 已到 | 叠戴细链预热讨论相对基线启动 | pending，本导出不写 hit |
| 2026-11-15 | TTS 窗中核 | 未到期 | 开窗后项链/layering∩gift 代理抬升 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | BFCM 后公开代理是否支撑测款+预热动作 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 250, 304, 282, 305, 260, 237 → 258

主指标与 镀金中粗圈耳环、友谊串珠手链、现货欧泊/字母吊坠 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 250 | — | — | observed |
| 2026-10-28 | 基线 | 304 | — | +21.6 | observed |
| 2026-10-29 | 基线 | 282 | — | -7.2 | observed |
| 2026-10-30 | 基线 | 305 | — | +8.2 | observed |
| 2026-10-31 | 基线 | 260 | — | -14.8 | observed |
| 2026-11-01 | 基线 | 237 | — | -8.8 | observed |
| 2026-11-11 | 评估窗 | 258 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 15 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 896482 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

叠戴细链套装 的冻结动作是「测款+预热」（预测秩 2）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 友谊串珠手链

English SKU：`friendship/beaded charm bracelet`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 3 |
| 冻结动作 predicted_action | 轻测 |
| 对照用动作 | 轻测 |
| urgency | 4.0 |
| demand | 5.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 18.0/20 |
| price_band | $8-22 |

- 发酵窗：2026-11-10 .. 2026-11-20
- 高峰窗：2026-11-20 .. 2026-11-30
- verify_by：2026-12-01
- 冻结时的窗假设：轻测礼品向串珠，发酵偏 TTS 开窗后；峰在送礼段（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-15 | 轻测中段核 | 未到期 | 串珠/友谊手链礼品向公开讨论是否出现 | 未到期，不提前填 actual |
| 2026-11-20 | 发酵末端核 | 未到期 | 发酵窗末端是否仍维持或抬升 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | 轻测路径事后公开代理回看 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 250, 304, 282, 305, 260, 237 → 258

主指标与 镀金中粗圈耳环、叠戴细链套装、现货欧泊/字母吊坠 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 250 | — | — | observed |
| 2026-10-28 | 基线 | 304 | — | +21.6 | observed |
| 2026-10-29 | 基线 | 282 | — | -7.2 | observed |
| 2026-10-30 | 基线 | 305 | — | +8.2 | observed |
| 2026-10-31 | 基线 | 260 | — | -14.8 | observed |
| 2026-11-01 | 基线 | 237 | — | -8.8 | observed |
| 2026-11-11 | 评估窗 | 258 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 3101708 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

友谊串珠手链 的冻结动作是「轻测」（预测秩 3）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 现货欧泊/字母吊坠

English SKU：`opal/birthstone/initial pendant (ready-stock)`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 4 |
| 冻结动作 predicted_action | 测款 |
| 对照用动作 | 测款 |
| urgency | 4.0 |
| demand | 5.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 18.0/20 |
| price_band | $18-45 |

- 发酵窗：2026-11-08 .. 2026-11-18
- 高峰窗：2026-11-11 .. 2026-11-30
- verify_by：2026-12-01
- 冻结时的窗假设：现货吊坠非全定制；开窗种草→BFCM 送礼峰（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-15 | 现货吊坠开窗核 | 未到期 | 现货欧泊/字母吊坠公开种草代理抬升（强调非全定制） | 未到期，不提前填 actual |
| 2026-11-22 | 送礼段中核 | 未到期 | 感恩节前吊坠∩gift 代理是否延续 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | 现货路径是否跑完可验证抬升 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 250, 304, 282, 305, 260, 237 → 258

主指标与 镀金中粗圈耳环、叠戴细链套装、友谊串珠手链 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 250 | — | — | observed |
| 2026-10-28 | 基线 | 304 | — | +21.6 | observed |
| 2026-10-29 | 基线 | 282 | — | -7.2 | observed |
| 2026-10-30 | 基线 | 305 | — | +8.2 | observed |
| 2026-10-31 | 基线 | 260 | — | -14.8 | observed |
| 2026-11-01 | 基线 | 237 | — | -8.8 | observed |
| 2026-11-11 | 评估窗 | 258 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 139231 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

现货欧泊/字母吊坠 的冻结动作是「测款」（预测秩 4）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 节日甲片

English SKU：`holiday press-on nails`。主指标：美甲美妆（`nail_makeup_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 5 |
| 冻结动作 predicted_action | 测款 |
| 对照用动作 | 测款 |
| urgency | 5.0 |
| demand | 4.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 18.0/20 |
| price_band | $8-18 |

- 发酵窗：2026-11-03 .. 2026-11-09
- 高峰窗：2026-11-11 .. 2026-11-20
- verify_by：2026-12-01
- 冻结时的窗假设：赶 Sephora 窗（至 11/9）发酵最早；峰可延到 TTS 前半（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-09 | Sephora 窗截止核 | 已到 | Sephora 结束日节日甲片公开代理是否已热/可测 | pending，本导出不写 hit |
| 2026-11-15 | TTS 延续核 | 未到期 | 开窗后甲片代理是否延续到 TTS | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | 早发酵品类窗后公开代理总结 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 167（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 122, 117, 106, 105, 109, 121 → 167

主指标与 唇膏小礼盒 共用（`nail_makeup_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 122 | — | — | observed |
| 2026-10-28 | 基线 | 117 | — | -4.1 | observed |
| 2026-10-29 | 基线 | 106 | — | -9.4 | observed |
| 2026-10-30 | 基线 | 105 | — | -0.9 | observed |
| 2026-10-31 | 基线 | 109 | — | +3.8 | observed |
| 2026-11-01 | 基线 | 121 | — | +11.0 | observed |
| 2026-11-11 | 评估窗 | 167 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 18 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 820518 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

节日甲片 的冻结动作是「测款」（预测秩 5）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 唇膏小礼盒

English SKU：`lip butter gift set`。主指标：美甲美妆（`nail_makeup_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 6 |
| 冻结动作 predicted_action | 测款+预热 |
| 对照用动作 | 测款+预热 |
| urgency | 5.0 |
| demand | 4.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 18.0/20 |
| price_band | $12-28 |

- 发酵窗：2026-11-03 .. 2026-11-12
- 高峰窗：2026-11-11 .. 2026-11-28
- verify_by：2026-12-01
- 冻结时的窗假设：美妆小礼借 Sephora+TTS 双窗；预热早、成交峰 BFCM 前（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-09 | Sephora 窗美妆核 | 已到 | 唇膏小礼在 Sephora 窗内公开代理热 | pending，本导出不写 hit |
| 2026-11-20 | BFCM 前峰核 | 未到期 | 开窗后唇膏礼盒代理进入抬升或维持 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | 测款+预热动作是否被公开代理验证 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 167（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 122, 117, 106, 105, 109, 121 → 167

主指标与 节日甲片 共用（`nail_makeup_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 122 | — | — | observed |
| 2026-10-28 | 基线 | 117 | — | -4.1 | observed |
| 2026-10-29 | 基线 | 106 | — | -9.4 | observed |
| 2026-10-30 | 基线 | 105 | — | -0.9 | observed |
| 2026-10-31 | 基线 | 109 | — | +3.8 | observed |
| 2026-11-01 | 基线 | 121 | — | +11.0 | observed |
| 2026-11-11 | 评估窗 | 167 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 16 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 381904 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

唇膏小礼盒 的冻结动作是「测款+预热」（预测秩 6）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### squishy 多件装

English SKU：`soft squishy multipack`。主指标：squishy/毛绒（`squishy_plush_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 7 |
| 冻结动作 predicted_action | 轻测 |
| 对照用动作 | 轻测 |
| urgency | 3.0 |
| demand | 4.0 |
| content | 5.0 |
| fulfill | 4.0 |
| 总分 | 16.0/20 |
| price_band | $8-20 |

- 发酵窗：2026-11-10 .. 2026-11-25
- 高峰窗：2026-11-26 .. 2026-11-30
- verify_by：2026-12-01
- 冻结时的窗假设：解压/小礼发酵在开窗后；峰对齐感恩节周末（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-15 | 开窗后轻测核 | 未到期 | 潮玩/squishy 礼品向公开讨论启动 | 未到期，不提前填 actual |
| 2026-11-27 | 感恩节周峰核 | 未到期 | 感恩节周末解压小礼公开代理是否抬 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | 轻测路径事后公开代理 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 122（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 89, 111, 101, 112, 86, 104 → 122

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 89 | — | — | observed |
| 2026-10-28 | 基线 | 111 | — | +24.7 | observed |
| 2026-10-29 | 基线 | 101 | — | -9.0 | observed |
| 2026-10-30 | 基线 | 112 | — | +10.9 | observed |
| 2026-10-31 | 基线 | 86 | — | -23.2 | observed |
| 2026-11-01 | 基线 | 104 | — | +20.9 | observed |
| 2026-11-11 | 评估窗 | 122 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 69378834 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

squishy 多件装 的冻结动作是「轻测」（预测秩 7）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

squishy 多件装：lead_days=12，冻结时按长链路情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是日桶未齐。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 法兰绒家庭 PJs

English SKU：`matching family Christmas PJs flannel`。主指标：时尚礼赠（`fashion_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 8 |
| 冻结动作 predicted_action | 轻测+内容 |
| 对照用动作 | 轻测+内容 |
| urgency | 3.0 |
| demand | 4.0 |
| content | 5.0 |
| fulfill | 3.0 |
| 总分 | 15.0/20 |
| price_band | 成人$18-35 / 家庭$45-80 |

- 发酵窗：2026-11-15 .. 2026-12-10
- 高峰窗：2026-11-26 .. 2026-12-15
- verify_by：2026-12-20
- 冻结时的窗假设：圣诞家庭套装发酵偏晚、长尾到 12 月中；verify 延至 12/20（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-20 | 内容启动核 | 未到期 | 家庭圣诞 PJs 内容/穿搭代理是否启动 | 未到期，不提前填 actual |
| 2026-12-01 | BFCM 后中核 | 未到期 | 感恩节/BFCM 后 PJs 公开代理是否进入送礼抬升 | 未到期，不提前填 actual |
| 2026-12-20 | 圣诞长尾核 | 未到期 | 长尾送礼段公开代理是否兑现发酵窗 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 245（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 193, 217, 199, 277, 211, 236 → 245

主指标与 燕麦色宽松粗针毛衣 共用（`fashion_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 193 | — | — | observed |
| 2026-10-28 | 基线 | 217 | — | +12.4 | observed |
| 2026-10-29 | 基线 | 199 | — | -8.3 | observed |
| 2026-10-30 | 基线 | 277 | — | +39.2 | observed |
| 2026-10-31 | 基线 | 211 | — | -23.8 | observed |
| 2026-11-01 | 基线 | 236 | — | +11.8 | observed |
| 2026-11-11 | 评估窗 | 245 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 11 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 9885681 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

法兰绒家庭 PJs 的冻结动作是「轻测+内容」（预测秩 8）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

法兰绒家庭 PJs：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是日桶未齐。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

### 燕麦色宽松粗针毛衣

English SKU：`cream/oatmeal oversized chunky knit`。主指标：时尚礼赠（`fashion_gift_posts`）。

#### 预测情况

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 9 |
| 冻结动作 predicted_action | 内容预热 |
| 对照用动作 | 内容预热 |
| urgency | 3.0 |
| demand | 4.0 |
| content | 5.0 |
| fulfill | 3.0 |
| 总分 | 15.0/20 |
| price_band | 内容向 |

- 发酵窗：2026-11-05 .. 2026-11-25
- 高峰窗：2026-11-26 .. 2026-11-30
- verify_by：2026-12-01
- 冻结时的窗假设：动作是内容预热：发酵看穿搭/讨论代理，成交峰 BFCM；hit 偏内容非强转化（预测）

| 日期 | 标签 | 是否已到 | 预期公开信号 | 本导出的对照 |
| --- | --- | --- | --- | --- |
| 2026-11-12 | 内容起量核 | 已到 | oversized/oatmeal knit 穿搭内容代理是否起量 | pending，本导出不写 hit |
| 2026-11-28 | BFCM 内容峰核 | 未到期 | BFCM 期间针织穿搭公开讨论是否维持/抬升 | 未到期，不提前填 actual |
| 2026-12-01 | 窗后回看 | 未到期 | 内容预热路径事后公开代理回看 | 未到期，不提前填 actual |

#### 数据爬坡

基线 2026-10-26 .. 2026-11-01 日均 —（6/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 245（1/1 日有数）。窗口帖量合计 —。形态：日桶未齐。基线或评估窗有缺失日。缺失保持 pending，不写成 0。

帖量曲线（基线 → 评估窗）：—, 193, 217, 199, 277, 211, 236 → 245

主指标与 法兰绒家庭 PJs 共用（`fashion_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 基线 | — | — | — | pending |
| 2026-10-27 | 基线 | 193 | — | — | observed |
| 2026-10-28 | 基线 | 217 | — | +12.4 | observed |
| 2026-10-29 | 基线 | 199 | — | -8.3 | observed |
| 2026-10-30 | 基线 | 277 | — | +39.2 | observed |
| 2026-10-31 | 基线 | 211 | — | -23.8 | observed |
| 2026-11-01 | 基线 | 236 | — | +11.8 | observed |
| 2026-11-11 | 评估窗 | 245 | — | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 837603 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

燕麦色宽松粗针毛衣 的冻结动作是「内容预热」（预测秩 9）。基线或评估窗的完整日桶不齐，或基线不能做比。这次不复核这条建议，也不把缺口写成没有需求。

燕麦色宽松粗针毛衣：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是日桶未齐。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。

pending 备注：Pending: missing full evaluation/baseline days or zero baseline; never impute actual.

## T1_2026-11-08_top9

- 冻结日：2026-11-08；状态：hard
- 标签：director_v1 hard
- 冻结备注：New Live five-dimension baseline; T0 unchanged
- 基线窗：2026-11-01 .. 2026-11-07（冻结日当天不计入）
- 有效样本 n=9，pending=0，Spearman=-0.2635，rank MAE=3.667
- 汇总说明：Public proxy only; rank MAE recomputed on common valid subset; category duplicates not independent. No model calibration until multiple independent windows.

### 节日甲片

English SKU：`holiday press-on nails`。主指标：美甲美妆（`nail_makeup_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「测款」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 1 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 测款 |
| urgency | — |
| demand | 2.3 |
| content | 2.7 |
| fulfill | 4.2 |
| 总分 | 17.2/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 2.3 | 2.7 | 4.2 | 3.9 | 3.5 | 17.2 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 5，动作「测款」，总分 18.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 140.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 167（1/1 日有数）。窗口帖量合计 167。形态：爬坡。相对增长 +18.8%。评估窗日均高于冻结前 7 日日均，路径不是冲高回落。

帖量曲线（基线 → 评估窗）：120, 164, 141, 123, 151, 145, 140 → 167

主指标与 唇膏小礼盒 共用（`nail_makeup_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 120 | 0.854 | — | observed |
| 2026-11-02 | 基线 | 164 | 1.167 | +36.7 | observed |
| 2026-11-03 | 基线 | 141 | 1.003 | -14.0 | observed |
| 2026-11-04 | 基线 | 123 | 0.875 | -12.8 | observed |
| 2026-11-05 | 基线 | 151 | 1.074 | +22.8 | observed |
| 2026-11-06 | 基线 | 145 | 1.032 | -4.0 | observed |
| 2026-11-07 | 基线 | 140 | 0.996 | -3.4 | observed |
| 2026-11-11 | 评估窗 | 167 | 1.188 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 18 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 820518 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

节日甲片 在 1 个评估日上，公开主指标相对冻结前 7 日日均 +18.8%，形态爬坡。与冻结动作「测款」同向，只记初步迹象。窗口太短，不能说这条测款或预热已经站得住。 主指标与 唇膏小礼盒 共用，这个判断不是该 SKU 的独立订单证据。

### 现货欧泊/字母吊坠

English SKU：`opal/birthstone/initial pendant (ready-stock)`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「测款」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 2 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 测款 |
| urgency | — |
| demand | 1.9 |
| content | 2.6 |
| fulfill | 4.2 |
| 总分 | 16.2/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 1.9 | 2.6 | 4.2 | 3.1 | 4.0 | 16.2 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 4，动作「测款」，总分 18.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 266.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 258。形态：走平。相对增长 -3.2%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：235, 281, 292, 305, 253, 256, 244 → 258

主指标与 叠戴细链套装、友谊串珠手链、镀金中粗圈耳环 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 235 | 0.882 | — | observed |
| 2026-11-02 | 基线 | 281 | 1.054 | +19.6 | observed |
| 2026-11-03 | 基线 | 292 | 1.095 | +3.9 | observed |
| 2026-11-04 | 基线 | 305 | 1.144 | +4.5 | observed |
| 2026-11-05 | 基线 | 253 | 0.949 | -17.0 | observed |
| 2026-11-06 | 基线 | 256 | 0.960 | +1.2 | observed |
| 2026-11-07 | 基线 | 244 | 0.915 | -4.7 | observed |
| 2026-11-11 | 评估窗 | 258 | 0.968 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 139231 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

现货欧泊/字母吊坠 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 2 的「测款」升格成伪热结论。 主指标与 叠戴细链套装、友谊串珠手链、镀金中粗圈耳环 共用，这个判断不是该 SKU 的独立订单证据。

### 叠戴细链套装

English SKU：`layering/paperclip necklace set`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「测款+预热」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 3 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 测款+预热 |
| urgency | — |
| demand | 1.9 |
| content | 2.6 |
| fulfill | 4.2 |
| 总分 | 16.0/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 1.9 | 2.6 | 4.2 | 3.4 | 3.5 | 16.0 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 2，动作「测款+预热」，总分 18.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 266.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 258。形态：走平。相对增长 -3.2%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：235, 281, 292, 305, 253, 256, 244 → 258

主指标与 现货欧泊/字母吊坠、友谊串珠手链、镀金中粗圈耳环 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 235 | 0.882 | — | observed |
| 2026-11-02 | 基线 | 281 | 1.054 | +19.6 | observed |
| 2026-11-03 | 基线 | 292 | 1.095 | +3.9 | observed |
| 2026-11-04 | 基线 | 305 | 1.144 | +4.5 | observed |
| 2026-11-05 | 基线 | 253 | 0.949 | -17.0 | observed |
| 2026-11-06 | 基线 | 256 | 0.960 | +1.2 | observed |
| 2026-11-07 | 基线 | 244 | 0.915 | -4.7 | observed |
| 2026-11-11 | 评估窗 | 258 | 0.968 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 15 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 896482 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

叠戴细链套装 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 3 的「测款+预热」升格成伪热结论。 主指标与 现货欧泊/字母吊坠、友谊串珠手链、镀金中粗圈耳环 共用，这个判断不是该 SKU 的独立订单证据。

### 友谊串珠手链

English SKU：`friendship/beaded charm bracelet`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「轻测」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 4 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 轻测 |
| urgency | — |
| demand | 1.9 |
| content | 2.6 |
| fulfill | 4.2 |
| 总分 | 16.0/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 1.9 | 2.6 | 4.2 | 3.1 | 3.8 | 16.0 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 3，动作「轻测」，总分 18.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 266.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 258。形态：走平。相对增长 -3.2%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：235, 281, 292, 305, 253, 256, 244 → 258

主指标与 现货欧泊/字母吊坠、叠戴细链套装、镀金中粗圈耳环 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 235 | 0.882 | — | observed |
| 2026-11-02 | 基线 | 281 | 1.054 | +19.6 | observed |
| 2026-11-03 | 基线 | 292 | 1.095 | +3.9 | observed |
| 2026-11-04 | 基线 | 305 | 1.144 | +4.5 | observed |
| 2026-11-05 | 基线 | 253 | 0.949 | -17.0 | observed |
| 2026-11-06 | 基线 | 256 | 0.960 | +1.2 | observed |
| 2026-11-07 | 基线 | 244 | 0.915 | -4.7 | observed |
| 2026-11-11 | 评估窗 | 258 | 0.968 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 3101708 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

友谊串珠手链 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 4 的「轻测」升格成伪热结论。 主指标与 现货欧泊/字母吊坠、叠戴细链套装、镀金中粗圈耳环 共用，这个判断不是该 SKU 的独立订单证据。

### 镀金中粗圈耳环

English SKU：`gold medium/chunky hoop earrings`。主指标：珠宝礼赠（`jewelry_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「测款」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 5 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 测款 |
| urgency | — |
| demand | 1.9 |
| content | 2.6 |
| fulfill | 4.2 |
| 总分 | 15.7/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 1.9 | 2.6 | 4.2 | 3.1 | 3.5 | 15.7 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 1，动作「测款」，总分 18.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 266.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 258（1/1 日有数）。窗口帖量合计 258。形态：走平。相对增长 -3.2%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：235, 281, 292, 305, 253, 256, 244 → 258

主指标与 现货欧泊/字母吊坠、叠戴细链套装、友谊串珠手链 共用（`jewelry_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 235 | 0.882 | — | observed |
| 2026-11-02 | 基线 | 281 | 1.054 | +19.6 | observed |
| 2026-11-03 | 基线 | 292 | 1.095 | +3.9 | observed |
| 2026-11-04 | 基线 | 305 | 1.144 | +4.5 | observed |
| 2026-11-05 | 基线 | 253 | 0.949 | -17.0 | observed |
| 2026-11-06 | 基线 | 256 | 0.960 | +1.2 | observed |
| 2026-11-07 | 基线 | 244 | 0.915 | -4.7 | observed |
| 2026-11-11 | 评估窗 | 258 | 0.968 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 13 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 28308 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

镀金中粗圈耳环 只有 1 个评估日，公开主指标 -3.2%，形态走平。短窗走弱或走平只记录方向，不把预测秩 5 的「测款」升格成伪热结论。 主指标与 现货欧泊/字母吊坠、叠戴细链套装、友谊串珠手链 共用，这个判断不是该 SKU 的独立订单证据。

### 唇膏小礼盒

English SKU：`lip butter gift set`。主指标：美甲美妆（`nail_makeup_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「测款+预热」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 6 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 测款+预热 |
| urgency | — |
| demand | 2.3 |
| content | 2.6 |
| fulfill | 4.2 |
| 总分 | 15.4/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 2.3 | 2.6 | 4.2 | 3.9 | 2.5 | 15.4 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 6，动作「测款+预热」，总分 18.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 140.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 167（1/1 日有数）。窗口帖量合计 167。形态：爬坡。相对增长 +18.8%。评估窗日均高于冻结前 7 日日均，路径不是冲高回落。

帖量曲线（基线 → 评估窗）：120, 164, 141, 123, 151, 145, 140 → 167

主指标与 节日甲片 共用（`nail_makeup_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 120 | 0.854 | — | observed |
| 2026-11-02 | 基线 | 164 | 1.167 | +36.7 | observed |
| 2026-11-03 | 基线 | 141 | 1.003 | -14.0 | observed |
| 2026-11-04 | 基线 | 123 | 0.875 | -12.8 | observed |
| 2026-11-05 | 基线 | 151 | 1.074 | +22.8 | observed |
| 2026-11-06 | 基线 | 145 | 1.032 | -4.0 | observed |
| 2026-11-07 | 基线 | 140 | 0.996 | -3.4 | observed |
| 2026-11-11 | 评估窗 | 167 | 1.188 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 16 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 381904 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

唇膏小礼盒 在 1 个评估日上，公开主指标相对冻结前 7 日日均 +18.8%，形态爬坡。与冻结动作「测款+预热」同向，只记初步迹象。窗口太短，不能说这条测款或预热已经站得住。 主指标与 节日甲片 共用，这个判断不是该 SKU 的独立订单证据。

### squishy 多件装

English SKU：`soft squishy multipack`。主指标：squishy/毛绒（`squishy_plush_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「轻测」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 7 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 轻测 |
| urgency | — |
| demand | 2.4 |
| content | 2.7 |
| fulfill | 2.1 |
| 总分 | 13.4/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 2.4 | 2.7 | 2.1 | 3.0 | 2.9 | 13.4 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 7，动作「轻测」，总分 16.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 122.71（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 122（1/1 日有数）。窗口帖量合计 122。形态：走平。相对增长 -0.6%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：104, 112, 106, 95, 177, 158, 107 → 122

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 104 | 0.848 | — | observed |
| 2026-11-02 | 基线 | 112 | 0.913 | +7.7 | observed |
| 2026-11-03 | 基线 | 106 | 0.864 | -5.4 | observed |
| 2026-11-04 | 基线 | 95 | 0.774 | -10.4 | observed |
| 2026-11-05 | 基线 | 177 | 1.442 | +86.3 | observed |
| 2026-11-06 | 基线 | 158 | 1.288 | -10.7 | observed |
| 2026-11-07 | 基线 | 107 | 0.872 | -32.3 | observed |
| 2026-11-11 | 评估窗 | 122 | 0.994 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 69378834 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

squishy 多件装 只有 1 个评估日，公开主指标 -0.6%，形态走平。短窗走弱或走平只记录方向，不把预测秩 7 的「轻测」升格成伪热结论。

squishy 多件装：lead_days=12，冻结时按长链路情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是走平。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。

### 法兰绒家庭 PJs

English SKU：`matching family Christmas PJs flannel`。主指标：时尚礼赠（`fashion_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「轻测+内容」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 8 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 轻测+内容 |
| urgency | — |
| demand | 2.0 |
| content | 2.6 |
| fulfill | 1.6 |
| 总分 | 12.6/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 2.0 | 2.6 | 1.6 | 1.8 | 4.0 | 12.6 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 8，动作「轻测+内容」，总分 15.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 238.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 245（1/1 日有数）。窗口帖量合计 245。形态：走平。相对增长 +2.7%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：235, 246, 227, 278, 209, 256, 219 → 245

主指标与 燕麦色宽松粗针毛衣 共用（`fashion_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 235 | 0.985 | — | observed |
| 2026-11-02 | 基线 | 246 | 1.031 | +4.7 | observed |
| 2026-11-03 | 基线 | 227 | 0.952 | -7.7 | observed |
| 2026-11-04 | 基线 | 278 | 1.165 | +22.5 | observed |
| 2026-11-05 | 基线 | 209 | 0.876 | -24.8 | observed |
| 2026-11-06 | 基线 | 256 | 1.073 | +22.5 | observed |
| 2026-11-07 | 基线 | 219 | 0.918 | -14.5 | observed |
| 2026-11-11 | 评估窗 | 245 | 1.027 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 11 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 9885681 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

法兰绒家庭 PJs 只有 1 个评估日，公开主指标 +2.7%，形态走平。短窗走弱或走平只记录方向，不把预测秩 8 的「轻测+内容」升格成伪热结论。 主指标与 燕麦色宽松粗针毛衣 共用，这个判断不是该 SKU 的独立订单证据。

法兰绒家庭 PJs：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是走平。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。

### 燕麦色宽松粗针毛衣

English SKU：`cream/oatmeal oversized chunky knit`。主指标：时尚礼赠（`fashion_gift_posts`）。

#### 预测情况

本行 predicted_action 是 Live hard freeze。回看对照采用 T0 原动作「内容预热」。两列都留在预测情况里。

| 字段 | 冻结时写下的值 |
| --- | --- |
| 预测秩 predicted_rank | 9 |
| 冻结动作 predicted_action | Live hard freeze |
| 对照用动作 | 内容预热 |
| urgency | — |
| demand | 2.0 |
| content | 2.6 |
| fulfill | 1.6 |
| 总分 | 11.5/25 |
| price_band | — |

这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。

| D | C | F | M | W | Live |
| --- | --- | --- | --- | --- | --- |
| 2.0 | 2.6 | 1.6 | 1.8 | 3.5 | 11.5 |

参照另一条冻结 T0_2026-11-02_top9：预测秩 9，动作「内容预热」，总分 15.0。这不是本条 freeze 行上的字段。

无 prediction_timing 记录。

无 prediction_checkpoints。

#### 数据爬坡

基线 2026-11-01 .. 2026-11-07 日均 238.57（7/7 日有数）。评估窗 2026-11-11 .. 2026-11-11 日均 245（1/1 日有数）。窗口帖量合计 245。形态：走平。相对增长 +2.7%。变化落在 ±10% 以内。

帖量曲线（基线 → 评估窗）：235, 246, 227, 278, 209, 256, 219 → 245

主指标与 法兰绒家庭 PJs 共用（`fashion_gift_posts`）。曲线相同，不是各自的订单。

| 日期 | 阶段 | 帖量 | 相对基线指数 | 日环比% | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-01 | 基线 | 235 | 0.985 | — | observed |
| 2026-11-02 | 基线 | 246 | 1.031 | +4.7 | observed |
| 2026-11-03 | 基线 | 227 | 0.952 | -7.7 | observed |
| 2026-11-04 | 基线 | 278 | 1.165 | +22.5 | observed |
| 2026-11-05 | 基线 | 209 | 0.876 | -24.8 | observed |
| 2026-11-06 | 基线 | 256 | 1.073 | +22.5 | observed |
| 2026-11-07 | 基线 | 219 | 0.918 | -14.5 | observed |
| 2026-11-11 | 评估窗 | 245 | 1.027 | — | observed |

指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。

#### 公开实际对照

下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。

| 日期 | 平台 | 渠道 | 指标 | 归属 | 数值 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | YouTube | public_search | sampled_video_count_snapshot | SKU | 19 | snapshot |
| 2026-11-11 | YouTube | public_search | sampled_video_views_snapshot | SKU | 837603 | snapshot |

数值为空的行：8。这些行不是 0 帖。涉及 GoogleTrends/search_velocity、Meta/reels_keyword_velocity、Reddit/complaint_share、Reddit/post_heat_7d、TikTok/content_velocity、TikTok/engagement_rate。

#### 对照解读

燕麦色宽松粗针毛衣 只有 1 个评估日，公开主指标 +2.7%，形态走平。短窗走弱或走平只记录方向，不把预测秩 9 的「内容预热」升格成伪热结论。 主指标与 法兰绒家庭 PJs 共用，这个判断不是该 SKU 的独立订单证据。

燕麦色宽松粗针毛衣：lead_days=16，冻结时按长链路情景；size_risk=0.9，冻结时按尺码敏感情景。us_ready_stock=false，没有美仓核验。这些是分析师先验，不是履约、退货或在途的实测。本窗公开声量形态是走平。声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。
