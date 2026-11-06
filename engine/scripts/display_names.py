# -*- coding: utf-8 -*-
"""Display-name map for exporters (T0 snapshot_json is immutable via trigger)."""

from __future__ import annotations

# Canonical Chinese display names. Prefer these over frozen snapshot_json zh_name
# when snapshot is wrong/English (esp. Top8 Pls→PJs historically, Top9 English).
ZH_NAME: dict[str, str] = {
    "gold medium/chunky hoop earrings": "镀金中粗圈耳环",
    "layering/paperclip necklace set": "叠戴细链套装",
    "friendship/beaded charm bracelet": "友谊串珠手链",
    "opal/birthstone/initial pendant (ready-stock)": "现货欧泊/字母吊坠",
    "holiday press-on nails": "节日甲片",
    "lip butter gift set": "唇膏小礼盒",
    "soft squishy multipack": "squishy 多件装",
    "matching family Christmas PJs flannel": "法兰绒家庭 PJs",
    "cream/oatmeal oversized chunky knit": "燕麦色宽松粗针毛衣",
}

# Apparel / size-sensitive / high-return clusters (fulfill time-decay targets)
APPAREL_SIZE_SENSITIVE: frozenset[str] = frozenset(
    {
        "matching family Christmas PJs flannel",
        "cream/oatmeal oversized chunky knit",
    }
)

# Low fulfill-decay (jewelry / nails / lip / squishy)
LOW_RETURN_CLUSTERS: frozenset[str] = frozenset(
    {
        "gold medium/chunky hoop earrings",
        "layering/paperclip necklace set",
        "friendship/beaded charm bracelet",
        "opal/birthstone/initial pendant (ready-stock)",
        "holiday press-on nails",
        "lip butter gift set",
        "soft squishy multipack",
    }
)

# metric_key → SKU clusters primarily driven by that public proxy
METRIC_TO_SKUS: dict[str, tuple[str, ...]] = {
    "jewelry_gift_posts": (
        "gold medium/chunky hoop earrings",
        "layering/paperclip necklace set",
        "friendship/beaded charm bracelet",
        "opal/birthstone/initial pendant (ready-stock)",
    ),
    "nail_makeup_gift_posts": (
        "holiday press-on nails",
        "lip butter gift set",
    ),
    "squishy_plush_gift_posts": ("soft squishy multipack",),
    "fashion_gift_posts": (
        "matching family Christmas PJs flannel",
        "cream/oatmeal oversized chunky knit",
    ),
    # TTS gift/holiday: channel momentum for gift-able SKUs (not apparel-heavy)
    "tts_us_gift_holiday_posts": (
        "gold medium/chunky hoop earrings",
        "layering/paperclip necklace set",
        "friendship/beaded charm bracelet",
        "opal/birthstone/initial pendant (ready-stock)",
        "holiday press-on nails",
        "lip butter gift set",
        "soft squishy multipack",
    ),
    "gift_guide_posts": (
        "gold medium/chunky hoop earrings",
        "layering/paperclip necklace set",
        "friendship/beaded charm bracelet",
        "opal/birthstone/initial pendant (ready-stock)",
        "holiday press-on nails",
        "lip butter gift set",
        "soft squishy multipack",
    ),
}

# Primary metric per SKU (for DoD / slope attribution)
SKU_PRIMARY_METRIC: dict[str, str] = {
    "gold medium/chunky hoop earrings": "jewelry_gift_posts",
    "layering/paperclip necklace set": "jewelry_gift_posts",
    "friendship/beaded charm bracelet": "jewelry_gift_posts",
    "opal/birthstone/initial pendant (ready-stock)": "jewelry_gift_posts",
    "holiday press-on nails": "nail_makeup_gift_posts",
    "lip butter gift set": "nail_makeup_gift_posts",
    "soft squishy multipack": "squishy_plush_gift_posts",
    "matching family Christmas PJs flannel": "fashion_gift_posts",
    "cream/oatmeal oversized chunky knit": "fashion_gift_posts",
}

METRIC_LABELS = {
    "bfcm_posts": "BFCM",
    "gift_guide_posts": "礼单 gift_guide",
    "tts_us_gift_holiday_posts": "TTS 礼/假日",
    "jewelry_gift_posts": "珠宝礼赠",
    "nail_makeup_gift_posts": "美甲美妆",
    "fashion_gift_posts": "时尚礼赠",
    "squishy_plush_gift_posts": "squishy/毛绒",
}

METRIC_ORDER = [
    "bfcm_posts",
    "gift_guide_posts",
    "tts_us_gift_holiday_posts",
    "jewelry_gift_posts",
    "nail_makeup_gift_posts",
    "fashion_gift_posts",
    "squishy_plush_gift_posts",
]

FREEZE_ID = "T0_2026-11-02_top9"
BLACK_FRIDAY = "2026-11-27"  # Thanksgiving 2026-11-26 next-day Friday
CATALYST_K = 1.0  # Rolling_Score += clamp(sum(weights)*K, -2, +2)
FORMULA_VERSION = "director_v1"


def zh_name(sku_cluster: str, snap_zh: str | None = None) -> str:
    """Always prefer exporter map over frozen snapshot when map has an entry."""
    if sku_cluster in ZH_NAME:
        return ZH_NAME[sku_cluster]
    if snap_zh:
        return snap_zh
    return sku_cluster
