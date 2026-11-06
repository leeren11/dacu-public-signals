# 大促公开信号日更 · 公开存证

Walk-forward 公开代理日更存证仓（非成交/非站内私有数据）。

## 边界

- 只存**公开代理**：公开帖量、内容热度代理、日历锚点、四维打分与动作建议。
- **不编造 GMV / 成交 / 站内私有数据**。
- `is_partial=1` 表示当日 UTC/采集窗未完。
- 已冻结预测 `T0_2026-11-02_top9`（soft）**禁止改预测字段**；规则变更只能新开 `freeze_id`。
- 回测 actual 侧只用事后可复核的公开代理。

## Dual-Track（自 2026-11-03 起）

- **Track A / T0**：`freeze/T0_2026-11-02_top9.md` 分数与排名为 12/01 回测标尺（勿改）。
- **Track B / Live Rolling**：`daily/YYYY-MM-DD.md` 含 `Rolling_Score / Rolling_Rank / Rank_Delta`，由完整日桶 DoD% + slope_7d + 履约时间衰减 + `external_catalysts.json` 合成。
- 每日 MD 同时包含 **昨日完整日桶主表**（完整值 / DoD% / slope_7d）与当日 partial 表。
- 日历锚点 **Black_Friday = 2026-11-27**（感恩节 11/26 次日周五）。
- Hard Freeze 11/08–11/09：T1 应从最新 Rolling 排名另开 freeze，禁止改 T0。

## 目录

- `daily/YYYY-MM-DD.md` — 每日公开信号快照 + 双轨 Top9（Git 提交时间即时间戳）
- `freeze/T0_2026-11-02_top9.md` — 软冻结 Top9 基线（只读存证）

## 账户与用途

- GitHub：`leeren11/dacu-public-signals`（公开）
- 用途：作品集 walk-forward 时间戳；方法由人讲，工具加速取数

生成于 2026-11-06 Asia/Shanghai（Dual-Track 升级后重渲）。
