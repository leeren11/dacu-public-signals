# Walk-forward 公开证据

这些文件是评估节点 **2026-11-12** 与 **2026-12-01** 的公开回看存证（见 `engine/config/retail_calendar.json` 的 `evaluations`）。

评估日流水线先跑 `backfill_actuals.evaluate`，再导出日更，所以当天的 `daily/` 能带上本次回看摘要。`evaluate` 把下面两份文件写入本目录，并在运行时 `reports/` 留一份副本：

- `walkforward_YYYY-MM-DD.md`：给运营总监读的回看。含一页结论、运营结论，以及每个冻结 SKU 的**预测情况**（秩、动作、分数、冻结时的窗假设）、**数据爬坡**（冻结前 7 日基线对评估窗的逐日帖量、指数和日环比）、**公开实际对照**（评估窗里已经入库的其他平台行；空行保持空，不当成 0）。
- `walkforward_YYYY-MM-DD.json`：同一内容的机器存证。`summary` 里有 n、Spearman、rank MAE；每个 SKU 另有 `climb.series`、冻结字段和平台行。

数字来自公开 X 完整 UTC 帖量，以及库里真实存在的 `platform_signals`。相对增长 = 评估窗日均 / 冻结前 7 日日均 − 1。同类目 SKU 可能共用一条曲线。缺日桶或基线不能做比时为 pending，不补 0，不编造销量或 GMV，不写准确率，也不填 action_hit / timing_hit。

Black_Friday 保持 `2026-11-27`。T0 原文不修改。

例行只提交本目录里已经生成的文件。建议提交说明：

```
walkforward: YYYY-MM-DD
```
