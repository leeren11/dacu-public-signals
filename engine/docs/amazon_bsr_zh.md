# Amazon BSR 证据层操作说明

这一层只保存 Amazon US（Keepa `domain=1`）的映射、原始证据、观测和独立派生指标。它不改 T0（2026-11-02）、T1（2026-11-08），不改 2026-11-12 与 2026-12-01 的回测定义或权重，也不把任何 Amazon 数字写进 Live 分数。

本说明里的命令由父执行器在运行时目录执行。提交这份代码的环境没有打开 `/workspace/dacu-signal/db/dacu_signals.sqlite`，也没有在那台机器上完成迁移。

仓库里的入口是 `engine/scripts/amazon_bsr_cli.py`。部署到运行时后，同一文件在：

```bash
cd /workspace/dacu-signal
python3 scripts/amazon_bsr_cli.py --help
```

数据库不进 git。原始 Keepa JSON 默认也不进公开导出。

## 现在还缺什么

- **ASIN 池是空的。** 四个目标组已登记，状态都是 `needs_input`。没有示例 ASIN，也不能把测试前缀 `B0EXAMPL` 写进正式库。每组建议 3 到 5 个你自己核对过的美国站 ASIN；0 个是允许的，表示还要补输入。
- **不需要 KEEPA_API_KEY 也能导入离线文件。** 没有这把钥匙时，实时采集的状态是 `unavailable`，退出码 0，不会发请求，也不让每日流水线失败。
- 离线文件要你自己从已有的 Keepa 响应保存。本仓库不附带真实响应。

## 迁移

先看会做什么。这一步不写库，也不做备份。

```bash
cd /workspace/dacu-signal
python3 scripts/amazon_bsr_cli.py migrate \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --dry-run
```

确认输出里 `drops` 是空数组、`preserves_existing_tables` 为 true 之后再执行。已有库会先用 SQLite backup API 复制一份，做 `integrity_check`，并写出 sha256。备份目录可以改。

```bash
python3 scripts/amazon_bsr_cli.py migrate \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --backup-dir /workspace/dacu-signal/db/backups
```

这次备份写在本机路径上。**它不是异地备份。** 复制到另一台机器或另一块介质才算异地，本工具不会声称已经做到。

迁移只新增 `amazon_*` 表、索引、触发器和视图，并在 `schema_migrations` 写入 `amazon_bsr_v1`。它不删除旧表，不改预测、冻结、滚动分数、walk-forward 或 X 信号。重复执行会返回 `already_applied`。

单独再做一次本机备份：

```bash
python3 scripts/amazon_bsr_cli.py backup \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --dest /workspace/dacu-signal/db/backups/manual.sqlite
```

目标文件已存在时会拒绝覆盖。

## 映射：sku_cluster → ASIN

四个组的名字必须和现有 sku 目录一致：

- `holiday press-on nails`
- `opal/birthstone/initial pendant (ready-stock)`
- `friendship/beaded charm bracelet`
- `soft squishy multipack`

先生成空模板。模板里没有 ASIN。填完 `mapping_version`、`valid_from`、`provenance` 后删掉 `_template` 再导入。

```bash
python3 scripts/amazon_bsr_cli.py mapping-template \
  --out /workspace/dacu-signal/data/amazon_mapping.template.json
```

`opal/birthstone/initial pendant (ready-stock)` 不能把三种属性糊成一个值。`product_attributes.pendant_facet` 只能是 `opal`、`birthstone`、`initial` 之一。若一件商品确实同时具备第二种刻面，必须另给 `additional_facets` 和至少 12 个字的 `multi_facet_reason`。手链同样用单一 `style_facet`（`friendship`、`beaded` 或 `charm`）。squishy 必须是 `product_form=squishy` 且 `pack_count` 为大于等于 2 的整数。

子体要写 `role=child`、不同的 `parent_asin`，以及这条子体自己的 `variation_attributes`。导入 Keepa 的 `variations` 只会记在证据表里，不会自动进入池子。

空的 `items` 不会删除已有映射。要退出一个 ASIN，放进同组的 `retire`，并写原因。同一 ASIN 不能同时属于两个当前组。映射版本一经写入就不能改内容；要改就用新的 `mapping_version`。旧行保留，只是 `is_current` 被关掉。

```bash
python3 scripts/amazon_bsr_cli.py mapping-import \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --file /workspace/dacu-signal/data/amazon_mapping.json \
  --dry-run

python3 scripts/amazon_bsr_cli.py mapping-import \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --file /workspace/dacu-signal/data/amazon_mapping.json
```

池子状态：0 个 `needs_input`，1–2 个 `below_recommended`，3–5 个 `within_recommended`，多于 5 个 `above_recommended`。少于 3 个也可以导入，只是还没达到建议规模。

`valid_from` 是你主张的生效日。`recorded_at` 是写进这个库的时间。把 `valid_from` 倒填到 T0 之前，不会让这条映射在 T0 当时变成已知。评估链接看的是 `recorded_at`。

## 离线导入 Keepa JSON

文件可以是产品请求响应（含 `products`）、单个产品对象、产品数组，或 JSONL。先干跑。

```bash
python3 scripts/amazon_bsr_cli.py import-raw \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --file /workspace/dacu-signal/data/keepa_us.json \
  --domain 1 \
  --retrieved-at 2026-11-08T12:00:00Z \
  --dry-run

python3 scripts/amazon_bsr_cli.py import-raw \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --file /workspace/dacu-signal/data/keepa_us.json \
  --domain 1 \
  --retrieved-at 2026-11-08T12:00:00Z
```

`--domain` 必须显式写成 `1`。其它站点会拒绝。

时间要分开看：

- `observed_at`：Keepa 时间换成 UTC 之后的变化时刻。Keepa 时间 0 是 `2011-01-01T00:00:00Z`。公式是 `(keepaTime + 21564000) * 60` 秒。负值不当作时间。`listedSince` 为 0 或 -1 时，文档说的是「没有该时间」，不会被写成 2011-01-01。
- `retrieved_at`：这份文件被取回的时间。不传时，若响应里有 Unix 毫秒 `timestamp` 就用它，否则用导入时钟，并在结果里能看出来。
- `first_available_to_system`：本库第一次收下这批点的时间。历史回补的 `observed_at` 可以很早，但冻结当时系统还不知道。默认它就是导入时钟，不能把它写成 Keepa 的观测时间。

只有在你确实早就掌握这批数据、只是现在才迁进这个库时，才使用：

```bash
python3 scripts/amazon_bsr_cli.py import-raw \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --file /workspace/dacu-signal/data/keepa_us.json \
  --domain 1 \
  --known-since 2026-11-01T00:00:00Z \
  --known-since-reason "已在迁库前的只读归档中，不是 Keepa 观测时间"
```

同一规范 JSON 再导一次不会复制观测。同一个 `observed_at` 上数值变了，会新增一条 revision，不改旧行。证据表禁止 UPDATE 和 DELETE。

请求参数里的 `key`、token、password 会在入库前改成 `[REDACTED]`。原始文件若含钥匙，库存的是去掉钥匙之后的规范 JSON；`file_sha256` 仍对应读到的原始字节。钥匙不要写进命令行参数，只放环境变量 `KEEPA_API_KEY`。

### Keepa 字段怎么解

解码对齐 2026-11-08 读取的官方说明：<https://keepa.com/api-docs/product-object.html>、<https://keepa.com/api-docs/offer-object.html>、<https://keepa.com/api-docs/product.html>。官方示例用的是 Java / PHP SDK 和直接 HTTP，这里不依赖第三方 Python 包，以免离线文件还要装 SDK。

- `salesRanks` 的每个类目 id 是一条独立名次序列。A 类目的变化不能拿去解释 B 类目。
- `csv[3]` 是主销售名次，不是「所有类目」。它只在 `salesRankReferenceHistory` 能对上当时的类目时才进入指标。没有这段历史时，不会把当前 `salesRankReference` 套到整段过去上。
- 名次 `-1` 和小于等于 0 都不是有效名次，指标里是 NULL，不是 0。
- `csv` 下标以官方表为准，不猜测。带 shipping 的类型是三元组 `(时间, 价格, 运费)`，运费不加成价格。未知下标只留在原始 JSON 里，不当成价格或名次。`csv[31]` RENT 已退役。eBay 下标不当成亚马逊价格。
- 价格单位是站点最小货币单位。`domain=1` 记为 USD 分。`-1` 表示该区间没有报价。
- `NEW` / `USED` / `COLLECTIBLE` / `REFURBISHED`：2026-02-23 之前是最低标价，当天及之后是最低落地价。这个分界写在每个点上。
- `csv[16]` RATING 是 0 到 50 的整数，45 表示 4.5 星。超出范围不会除以 10。
- `csv[17]` 的枚举名是 `COUNT_REVIEWS`，文档定义是评分人数，不是文字评论数。
- `reviews.reviewCount` 才是变体维度的文字评论数。`reviews.ratingCount` 也是变体维度，且 Keepa 写明自 2025-04-09 起不再更新。这三条定义不会互相做差。
- 评分历史通常要请求带 `offers` 或 `rating=1` 才会出现，而且不是从商品上架日开始的完整史。缺席不是 0 星，也不是 0 条评论。
- `stockCSV` 只有载荷里真有才入库。Keepa 说明它是尽力估计，限购时可能不准。没有该字段不会补成 0 库存。`availabilityAmazon` 只是当前亚马逊自营可售代码，不是库存历史。
- `monthlySold` 是亚马逊「过去一个月购买量」的档位（如 100+），不是精确销量，更不是 GMV，不参与派生指标。
- 变体商品经常没有自己的销售名次。父体的名次不会抄给子体。

## 派生指标

默认不派生「加速度」。也没有 `amazon_signal_score`。

两条名次指标，版本名固定：

- `bsr_ln_ratio_7d_v1`：`ln(旧名次 / 新名次)`。旧名次是窗口起点，新名次是终点。名次数字变小则对数为正。这不是销量。
- `bsr_rank_improvement_pct_7d_v1`：`(旧名次 - 新名次) / 旧名次 * 100`。正数表示名次数字下降，也就是名次改善百分比，不是销售增长。

计数指标只在同一 `definition_variant` 上做绝对差（终点减起点）：

- `rating_count_abs_delta_7d_v1`
- `written_review_count_abs_delta_7d_v1`

日选择政策 `utc_day_latest_observed_at_lowest_revision_v1`：每个 UTC 日只留一个快照，取最晚的 `observed_at`，同一时刻取最小 `revision_seq`，再取最小 `observation_id`。不是当日中位数，也不会把没有点的日子用前值补上。

7 日窗口要求起点 UTC 日正好是终点 UTC 日减 7 天，而且两个快照的实际时间跨度落在 6 到 8 天。跨度、原始点数和日快照数会写在结果上。类目中途出现 `-1` 或参考类目在 `csv[3]` 窗口内切换时，值为 NULL，状态是 discontinuity，不当作连续移动。

不带 `--selection-cutoff` 时，截止时刻是「现在」，只表示当前库里已经知道的数据，输出会标明这不是冻结回放。要和某个冻结时点对照，截止时刻必须显式给出，而且早于该时刻才入库的回补不会被用上。

```bash
python3 scripts/amazon_bsr_cli.py derive \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --as-of 2026-11-08 \
  --selection-cutoff 2026-11-08T16:00:00Z \
  --dry-run

python3 scripts/amazon_bsr_cli.py derive \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --as-of 2026-11-08 \
  --selection-cutoff 2026-11-08T16:00:00Z
```

下面这条只在 `amazon_eval_link` 里记一个独立标签。它不读取、不修改 `prediction_*`、`live_freeze_*` 或 walk-forward 表。`T0_2026-11-02_top9` 与 `T1_2026-11-08_top9_hard` 只是你可以传入的标签。

```bash
python3 scripts/amazon_bsr_cli.py derive \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --as-of 2026-11-08 \
  --selection-cutoff 2026-11-08T16:00:00Z \
  --eval-freeze-id T1_2026-11-08_top9_hard \
  --eval-date 2026-11-08
```

派生结果同样只追加。同一输入再跑一次不会改旧值。

## 状态、健康、导出

```bash
python3 scripts/amazon_bsr_cli.py status \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite

python3 scripts/amazon_bsr_cli.py health \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite

python3 scripts/amazon_bsr_cli.py export \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --out /tmp/amazon_bsr_summary.json
```

`export` 默认不含原始 JSON。标准输出即使加了 `--include-raw` 也不打印载荷，只把载荷写进 `--out` 指向的文件。不要把那个文件提交进公开仓库。`--include-raw` 仍然是去掉钥匙之后的文本。

`status` / `health` 会给出每组池子状态、最近 `retrieved_at` 与 `observed_at`、评分字段是否缺席，以及 `live_api`。没有钥匙时是 `unavailable_no_key`。有钥匙但这次没有调用时是 `key_present_not_used`。二者都不会打印钥匙本身。

## 每日流水线

默认的每日命令不会导入 Amazon，也不会发实时请求，也不会改分数或冻结。

只有在迁移已经完成、而且你手头有本地文件时才加这个参数：

```bash
python3 scripts/run_daily_pipeline.py \
  --as-of 2026-11-08 \
  --skip-collect \
  --amazon-local-input /workspace/dacu-signal/data/keepa_us.json
```

这个钩子拒绝 URL。它在当日分数已经按原逻辑写完之后才读本地文件，失败也不会回滚分数。

## 实时 Keepa（默认关闭）

不带 `--live-fetch` 就不会请求。没有 `KEEPA_API_KEY` 时，即使带了该旗标，结果也是 `unavailable`，退出码 0，请求次数为 0。

钥匙只来自环境变量，不要写成 `--api-key`。

```bash
KEEPA_API_KEY="你的钥匙" python3 scripts/amazon_bsr_cli.py live-fetch \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --live-fetch \
  --domain 1 \
  --asin B0REALASIN1 \
  --token-budget 5 \
  --batch-size 1
```

`--token-budget` 和 `--batch-size` 都必须显式给出。预算是响应里 `tokensConsumed` 的累计上限，不是本工具算出来的预估。基础产品请求的公开说明是每个商品 1 token（<https://keepa.com/api-docs/product.html>）；这个数字只用来在下一次请求前停下，响应里的 `tokensConsumed` 才是记入数据库的消耗。若响应没有该字段，运行停止，不会编一个数。

默认请求带 `history=1`，不带 `rating`、`offers`、`stock`、`buybox`。因此默认响应里可能没有评分历史；缺席仍然不是 0。若要这些字段，必须 `--batch-size 1`，因为它们的额外 token 取决于 Keepa 当时的数据，本工具不去猜：

```bash
KEEPA_API_KEY="你的钥匙" python3 scripts/amazon_bsr_cli.py live-fetch \
  --db /workspace/dacu-signal/db/dacu_signals.sqlite \
  --live-fetch \
  --domain 1 \
  --asin B0REALASIN1 \
  --token-budget 5 \
  --batch-size 1 \
  --rating
```

实时拉取不会把 ASIN 自动写进映射池。

## 什么时候才可以考虑加权重

下面几条同时成立之前，不要把 Amazon 指标加进 Live，也不要改 2026-11-12 和 2026-12-01 的权重。即便都成立，也只是允许人工再决定，当前代码不会自动加权重。

1. 该组不是 `needs_input`。建议每组 3–5 个真实美国站 ASIN；不足或超出都要有书面接受，而不是用示例 ASIN 凑数。
2. 映射版本已经固定。opal / birthstone / initial 没有被混成一个属性；子体有自己的变体属性。
3. 每个准备加权的 ASIN，在同一 `domain_id=1` 和同一个类目上，至少有一条 `status=ok` 的 7 日指标，`span_days` 有值，两端类目相同，且没有 discontinuity。
4. 两端观测的 `first_available_to_system` 都不晚于评估截止时刻。冻结之后才回补的历史不能解释 T0 或 T1。
5. 评分人数和文字评论的差值各自使用自己的 `definition_variant`。`csv[17]` 不和 `reviews.reviewCount` 比较。`reviews.ratingCount` 不当作 2025-04-09 之后的现势人数。
6. 对数比和改善百分比在报告里仍然写成名次变化，不写成销量或 GMV。
7. T0、T1，以及 2026-11-12 与 2026-12-01 的原定义和权重保持原样。
8. 有一次单独的人工复核接受这条序列。在那之前，`live_score_integration` 保持 `not_validated`。

## 本地测试

在仓库的 `engine` 目录：

```bash
cd engine
python3 -m unittest tests.test_amazon_bsr -v
```

测试夹具带有 `_example` 和 `B0EXAMPL` 前缀，只存在于测试库。正式导入会拒绝它们。
