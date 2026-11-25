"""Independent evidence ledger and shadow demand score.

Version evidence_research_v2.1.0 does not replace director_v1, does not
rewrite freezes, and does not collect from the network.
"""

VERSION_ID = "evidence_research_v2.1.0"
FORMULA_ID = "shadow_demand_v2"
SCHEMA_VERSION = "7"
EXAMPLE_LABEL = "SYNTHETIC_EXAMPLE_NOT_PRODUCTION"

LAST30DAYS_REVIEW = {
    "repo": "https://github.com/mvanhorn/last30days-skill",
    "commit": "7c2e1c2b099b13abd4397910168c4f53e638bb21",
    "committed_at": "2026-11-24T11:37:45-08:00",
    "license": "MIT",
    "copyright": "Copyright (c) 2026 Matt Van Horn",
    "skill_version_read": "4.6.0",
    "executed_skill": False,
}

DISCLAIMER = (
    "shadow_demand_v2 只比较当时可见的公开帖量动量。"
    "source_coverage 不是预测概率，分数不是准确率，也不能外推销售、GMV 或备货。"
    "director_v1 与 T0/T1 冻结保持原样。"
)

COVERAGE_NOTE = (
    "source_coverage 是计划内官方日频源的完整窗口占比，不是预测概率，也不是准确率。"
)

COMPARE_NOTE = (
    "descriptive_rank_agreement 只描述 director_v1 名次与 shadow_demand_v2 动量名次是否同向，"
    "不是准确率、胜率或销售提升。共享类目不按 SKU 数重复计数。未评分的组保持 pending。"
)
