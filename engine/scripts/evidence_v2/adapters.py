"""Known source adapters. Missing official feeds stay missing; this module does not fetch."""

from __future__ import annotations

from dataclasses import dataclass

from evidence_v2 import VERSION_ID


@dataclass(frozen=True)
class Adapter:
    adapter_id: str
    platform: str
    cadence: str
    official_daily: bool
    availability: str
    reason: str

    def as_row(self) -> tuple:
        return (
            self.adapter_id,
            self.platform,
            self.cadence,
            1 if self.official_daily else 0,
            self.availability,
            self.reason,
            VERSION_ID,
        )


ADAPTERS: tuple[Adapter, ...] = (
    Adapter(
        "x_public_counts",
        "X",
        "daily",
        True,
        "available",
        "已有公开帖量日桶可由外部采集写入；本层不发起新的 X 请求。",
    ),
    Adapter(
        "google_trends_anchor_ratio",
        "GoogleTrends",
        "relative_index",
        False,
        "excluded",
        "相对锚点比值，不是搜索次数，也不能当作第二条独立帖量序列。",
    ),
    Adapter(
        "youtube_search_snapshot",
        "YouTube",
        "snapshot",
        False,
        "excluded",
        "采集日搜索样本或累计快照，不是日播放增量。",
    ),
    Adapter(
        "tiktok_monthly_background",
        "TikTok",
        "monthly",
        False,
        "excluded",
        "仅有月度背景；没有可证明的官方日频序列。",
    ),
    Adapter(
        "meta_ads",
        "Meta",
        "unavailable",
        False,
        "missing",
        "HTTP 403，官方日频不可用；缺失不是 0 投放。",
    ),
    Adapter(
        "reddit_public",
        "Reddit",
        "unavailable",
        False,
        "missing",
        "HTTP 403，公开 JSON 没有可用数值；缺失不是 0 差评。",
    ),
)

BY_PLATFORM = {item.platform: item for item in ADAPTERS}


def adapter_for(platform: str | None) -> Adapter | None:
    if platform is None:
        return None
    return BY_PLATFORM.get(platform)
