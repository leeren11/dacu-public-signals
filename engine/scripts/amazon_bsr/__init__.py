"""Independent Amazon BSR evidence layer. Not an input to Live scores."""

SCHEMA_VERSION = "amazon_bsr_v1"
POLICY_ID = "utc_day_latest_observed_at_lowest_revision_v1"

METRIC_LN = "bsr_ln_ratio_7d_v1"
METRIC_PCT = "bsr_rank_improvement_pct_7d_v1"
METRIC_RATING_COUNT = "rating_count_abs_delta_7d_v1"
METRIC_WRITTEN_REVIEWS = "written_review_count_abs_delta_7d_v1"

INTERPRET_LN = "ln_old_bsr_over_new_bsr_not_sales"
INTERPRET_PCT = "rank_improvement_percent_not_sales_growth"
INTERPRET_COUNT = "absolute_count_change_same_definition"
