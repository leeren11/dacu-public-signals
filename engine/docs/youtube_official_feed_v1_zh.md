# YouTube 官方 feed shadow 与归档修复

版本 `youtube_official_feed_v1`。未接入日更，不改 `director_v1`、T0/T1、旧评价，也不把新源写进 v2 分数。一次离线解析成功不是持续接通，7 个日更周期的验收还没有做。

## 归档根因

生产与公开仓里的 `collectors/human_fetch.py` 原先把 `json.dumps(...)` 切到 2,000,000 个字符，再把 `platform_raw` 的 body 切到 80,000 个字符并加上 `\n/* truncated */`（16 个字符）。这正好对应约 2MB 的 `Unterminated string`，以及 80016 字符的原始片段。截断发生在写盘，不能据此说线上解析全部失败。

现在缓存和 raw 都整份序列化后原子替换。超过上限时 JSON 仍然可解析，`truncated=1`，正文不写入，只留全文字节数、SHA256 和最多 200 字符的前缀。`read_good_cache` 不把坏 JSON、带旧切片标记或 `truncated=1` 的文件当有效源。旧的损坏文件保持原样，检查结果是 `legacy_truncated_invalid`。

## 条款

2026-11-25 读过 YouTube API Services Developer Policies（`developers.google.com/youtube/terms/developer-policies`）III.E。公开 Atom 地址一次 GET 成功，不等于获得再分发或商业存储许可；这个 feed 算不算 API Data 也不明确。因此：

- 只请求 `https://www.youtube.com/feeds/videos.xml?channel_id={UC...}`，不改域名、不跟随到别的主机、不下载视频文件。
- 统计值默认最多保留 30 天，`purge-expired` 会删过期证据。不允许把保留期设得更长。
- 累计 views 原样保存。`observed_cohort_views_delta` 只是两次快照的算术差，声明里写明它不是 YouTube 指标、不是日播放、不是销量，也不进评分。
- 间隔不是精确的 UTC 日界则 `partial`，并记下真实小时数。计数下降不裁成 0。

## 数据边界

默认观察名单只有 `EBANKUnail_official`（`UCp7db2pxQKGH1mI7D_Jxedg`），角色是品牌自营供给代理，`maps_to_sku=0`。凝胶贴标题不会自动当成 press-on。其他频道、YouTube 官方对照频道都不会自动变成类目覆盖。名单里只要 `maps_to_sku` 不是 0 就拒绝导入。

15 条是这次看到的 feed 窗口，不是完整历史。条数达到上限且跨度不足 24 小时时，原因是 `feed_cap_shorter_than_24h`。达到上限但跨度更长时仍是 `partial`（`feed_capped_eviction_possible`），因为删除风险没有被证明消失。指标名只用 `observed_recent_uploads`。

`published_at`、`feed_updated_at`、`retrieved_at`、`first_available_at` 分开存。对象第一次入库的 `first_available_at` 不会被更早的回填时间前移。

## 仍未接通

这些源只有禁用说明，没有新请求，也没有装插件或申请账号：

| 源 | 状态 |
| --- | --- |
| YouTube Data API | 未授权项目，实测 403 `ACCESS_DENIED`，不把它说成只缺 key |
| Reddit | JSON 403；已存 RSS 200 实际是 HTML 登录墙，现判 `auth_wall`，不是 0 |
| Meta | 403，官方说明本轮未核实 |
| Trends 官方 API | 仍是 alpha 申请；旧相对指数定义不动 |
| TikTok Research | 资格未确认；月度背景不是日频 |
| Keepa | 无 key，正式 ASIN 映射和 BSR 仍是 0 |

401/403 会把该频道记为 `stopped_auth`，之后不再请求。429 只在 `Retry-After` 不超过 5 秒时重试一次。5xx 和超时最多再试两次。没有代理。

## 测试

`python3 -m unittest tests.test_youtube_official_feed tests.test_collector_honesty tests.test_evidence_v2`：33 项通过。

其中真实样本 `/uploads/youtube_ebanku_candidate_2175.xml` 离线解析：15 条；`d23RxaInO1g` 累计 views=8；`xHWHamkgG-g` 累计 views=113；上传行 `partial`；2026-11-25 UTC 桶有更早锚点，但仍不记成完整日总量；`maps_to_sku=0`。这是对已提供样本的离线复核，不是新的在线连续验证。仓库里只提交了这两条的摘录 `examples/youtube_official_feed_excerpt.xml`，标记 `PUBLIC_FEED_EXCERPT_NOT_PRODUCTION`。同一摘录导入两次，evidence id 同为 `2d475c5b2c105484c0d99de40845f2b04d8f048abcdc370bdee4703bc87d6ce5`。

## 隔离库命令

在放有本增量的 `engine/` 或生产 `scripts/` 的上一级执行。数据库用单独文件，不要指向生产库。

```bash
python3 scripts/youtube_official_feed_cli.py migrate --db /tmp/youtube_feed_shadow.sqlite
python3 scripts/youtube_official_feed_cli.py approve-watchlist \
  --db /tmp/youtube_feed_shadow.sqlite \
  --watchlist examples/youtube_official_feed_watchlist.json
python3 scripts/youtube_official_feed_cli.py import-xml \
  --db /tmp/youtube_feed_shadow.sqlite \
  --xml examples/youtube_official_feed_excerpt.xml \
  --channel-id UCp7db2pxQKGH1mI7D_Jxedg \
  --watchlist-version 2026-11-25-shadow-review \
  --retrieved-at 2026-11-25T15:59:23+00:00 \
  --now 2026-11-26T00:10:00+00:00 \
  --archive-dir /tmp/youtube_feed_archive \
  --example-label PUBLIC_FEED_EXCERPT_NOT_PRODUCTION
python3 scripts/youtube_official_feed_cli.py disabled --db /tmp/youtube_feed_shadow.sqlite
python3 scripts/youtube_official_feed_cli.py rollback --db /tmp/youtube_feed_shadow.sqlite
```

`fetch` 已实现，但本轮没有再打官方端点。以后每个已批准频道、每个既有日更周期最多一次，而且不要从日更进程里调用，直到下面的 7 周期记录齐。

## 安装与回滚

只覆盖本轮改过的文件，不要整仓覆盖生产。必须替换的旧文件只有：

- `scripts/collectors/human_fetch.py`（归档写入）
- `scripts/collectors/public_sources.py`（HTML 登录墙不再当空 feed）

新增：

- `scripts/collectors/archive.py`
- `scripts/collectors/feed_honesty.py`
- `scripts/youtube_official_feed/`
- `scripts/youtube_official_feed_cli.py`
- `sql/migrate_v8_youtube_official_feed.sql`
- `examples/youtube_official_feed_excerpt.xml`
- `examples/youtube_official_feed_watchlist.json`
- `examples/reddit_login_wall_min.html`
- `tests/test_youtube_official_feed.py`
- `docs/youtube_official_feed_v1_zh.md`

回滚代码：撤下上述新增文件，并恢复这两个 collector 文件的上一版。回滚数据：

```bash
python3 scripts/youtube_official_feed_cli.py rollback --db /tmp/youtube_feed_shadow.sqlite
```

它只删除 `youtube_feed_*` 和迁移号 8。`director_v1`、冻结和 v2 影子分都不重算。

## 连续 7 个日更周期的验收

这是给父流程的规范，本 PR 没有执行。

1. 每个既有日更周期、每个批准频道最多一次官方 GET。禁止为了补 15 条窗口去加频率。
2. 每次尝试都要留下 evidence：`retrieved_at`、响应 SHA256、字节数、HTTP 状态、`status`。失败写明原因，不写 0。
3. 7 次都留证才算采集留证率 100%。成功目标可以按不少于 95% 看，但样本小，要同时写出失败条数。
4. 同一 `video_id` 至少两个快照之后，才可以读 `observed_cohort_views_delta`，并且必须带着真实 `hours_between`。没有上一个快照就没有增长。
5. `feed_cap_shorter_than_24h` 或仍有淘汰可能时，上传数保持 partial，不叫完整 UTC 日总量。
6. 7 天只说明采集能不能连续留下，不说明预测变准。权重仍要等更长的独立窗口。
7. 出现 401/403 就停该频道。不要改爬搜索页，不要换域名。
