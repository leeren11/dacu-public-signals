"""Identity, near-duplicate text, and engagement fields.

Near-duplicate detection follows the method in last30days-skill dedupe.py
(exact identity first, then hybrid Jaccard) at the pinned review commit.
Conflicting numeric values are kept as revisions. They are not merged.
Engagement counters follow the summable-field idea in schema.py: rank-like
fields are not added, and a missing count stays None.
"""

from __future__ import annotations

import hashlib
import json
import re

_NON_SUMMABLE = ("rank", "rating", "score", "ratio", "rate", "followers", "subscribers")


def canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in text.split() if len(token) > 1}


def _ngrams(text: str, size: int = 3) -> set[str]:
    compact = text.replace(" ", "")
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index:index + size] for index in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union)


def hybrid_similarity(left: str, right: str) -> float:
    """Character-trigram Jaccard or token Jaccard, whichever is larger."""
    a = normalize_text(left)
    b = normalize_text(right)
    return max(_jaccard(_ngrams(a), _ngrams(b)), _jaccard(_tokens(a), _tokens(b)))


def nonsummable_field(name: str) -> bool:
    lowered = name.lower()
    return lowered in _NON_SUMMABLE or lowered.endswith(("_rank", "_score", "_ratio", "_rate", "_followers"))


def engagement_counters(engagement: dict | None) -> dict:
    """Copy additive counters. Missing values stay None and are not coerced to 0."""
    if engagement is None:
        return {}
    kept = {}
    for key, value in engagement.items():
        if nonsummable_field(str(key)):
            continue
        kept[str(key)] = value
    return kept
