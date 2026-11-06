# 大促公开信号日更 · 公开存证

Walk-forward 公开代理日更存证仓（非成交/非站内私有数据）。

## 边界

- 只存**公开代理**：公开帖量、内容热度代理、日历锚点、四维打分与动作建议。
- **不编造 GMV / 成交 / 站内私有数据**。
- `is_partial=1` 表示当日 UTC/采集窗未完。
- 已冻结预测 `T0_2026-11-02_top9`（soft）**禁止改预测字段**；规则变更只能新开 `freeze_id`。
- 回测 actual 侧只用事后可复核的公开代理。

## 目录

- `daily/YYYY-MM-DD.md` — 每日公开信号快照 + Top 动作（Git 提交时间即时间戳）
- `freeze/T0_2026-11-02_top9.md` — 软冻结 Top9 基线（只读存证）

## 账户与用途

- GitHub：`leeren11/dacu-public-signals`（公开）
- 用途：作品集 walk-forward 时间戳；方法由人讲，工具加速取数

生成于 2026-11-06 12:08 Asia/Shanghai。
