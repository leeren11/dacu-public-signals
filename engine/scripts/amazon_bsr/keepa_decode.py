"""Decode a Keepa product object using the documented csv indexes and Keepa Time.

Source checked 2026-11-08:
https://keepa.com/api-docs/product-object.html
https://keepa.com/api-docs/offer-object.html
https://keepa.com/api-docs/product.html

New csv indexes are not treated as prices or ranks. csv[17] is the rating-count
history even though its enum name is COUNT_REVIEWS. reviews.reviewCount is the
variation-specific written-review history. Stock is stored only when stockCSV
(or another documented stock field) is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.redact import canonical_hash
from amazon_bsr.timeutil import keepa_minutes_to_utc

DOCS = "https://keepa.com/api-docs/product-object.html"
BLANK_CATEGORY = "9223372036854775807"
LANDING_PRICE_CUTOFF = "2026-02-23T00:00:00Z"
LISTING_PRICE_INDEXES = {1, 2, 5, 6}

# index, name, step (2 = time,value; 3 = time,price,shipping), family
# Families: price, sales, offer_count, rating, rating_count, meta, retired, ebay, trade_in
CSV_TYPES: dict[int, tuple[str, int, str]] = {
    0: ("AMAZON", 2, "price"),
    1: ("NEW", 2, "price"),
    2: ("USED", 2, "price"),
    3: ("SALES", 2, "sales"),
    4: ("LISTPRICE", 2, "price"),
    5: ("COLLECTIBLE", 2, "price"),
    6: ("REFURBISHED", 2, "price"),
    7: ("NEW_FBM_SHIPPING", 3, "price"),
    8: ("LIGHTNING_DEAL", 2, "price"),
    9: ("WAREHOUSE", 2, "price"),
    10: ("NEW_FBA", 2, "price"),
    11: ("COUNT_NEW", 2, "offer_count"),
    12: ("COUNT_USED", 2, "offer_count"),
    13: ("COUNT_REFURBISHED", 2, "offer_count"),
    14: ("COUNT_COLLECTIBLE", 2, "offer_count"),
    15: ("EXTRA_INFO_UPDATES", 2, "meta"),
    16: ("RATING", 2, "rating"),
    17: ("COUNT_REVIEWS", 2, "rating_count"),
    18: ("BUY_BOX_SHIPPING", 3, "price"),
    19: ("USED_NEW_SHIPPING", 3, "price"),
    20: ("USED_VERY_GOOD_SHIPPING", 3, "price"),
    21: ("USED_GOOD_SHIPPING", 3, "price"),
    22: ("USED_ACCEPTABLE_SHIPPING", 3, "price"),
    23: ("COLLECTIBLE_NEW_SHIPPING", 3, "price"),
    24: ("COLLECTIBLE_VERY_GOOD_SHIPPING", 3, "price"),
    25: ("COLLECTIBLE_GOOD_SHIPPING", 3, "price"),
    26: ("COLLECTIBLE_ACCEPTABLE_SHIPPING", 3, "price"),
    27: ("REFURBISHED_SHIPPING", 3, "price"),
    28: ("EBAY_NEW_SHIPPING", 3, "ebay"),
    29: ("EBAY_USED_SHIPPING", 3, "ebay"),
    30: ("TRADE_IN", 2, "trade_in"),
    31: ("RENT", 2, "retired"),
    32: ("BUY_BOX_USED_SHIPPING", 3, "price"),
    33: ("PRIME_EXCL", 2, "price"),
    34: ("COUNT_NEW_FBA", 2, "offer_count"),
    35: ("COUNT_NEW_FBM", 2, "offer_count"),
}

RATING_COUNT_REASON = (
    "Keepa csv index 17 is named COUNT_REVIEWS, but the product-object docs define it as "
    "the rating count history, not the written review count. Written reviews are "
    "reviews.reviewCount and are variation-specific. This history is not a full history "
    "from first listing; it is present only when the request used offers or rating=1."
)
WRITTEN_REVIEW_REASON = (
    "reviews.reviewCount is the variation-specific written review count. It is not "
    "csv[17] and is not the non-variation rating count. Keepa says this object cannot be force-updated."
)
RATING_COUNT_STALE_REASON = (
    "Keepa product-object docs: the reviews.ratingCount history has not been updated since "
    "April 9th 2025 because Amazon removed that data point. It is variation-specific and is "
    "not a current rating count. It is not csv[17]."
)
STOCK_REASON = (
    "stockCSV is present on this offer. Keepa describes it as a best effort that is not "
    "guaranteed and can be wrong when per-customer limits apply. A missing stockCSV is not zero stock."
)
SALES_CHANGE_ONLY = (
    "Keepa appends a history point only when the value changes. observed_at is that change "
    "time, not a daily sample. lastUpdate is the product update time, not this point's observed_at."
)
AVAILABILITY_NOTES = {
    -1: "no Amazon offer exists",
    0: "Amazon offer is in stock and shippable",
    1: "Amazon offer is not in stock now but will be (pre-order)",
    2: "Amazon offer availability is unknown",
    3: "Amazon offer is not in stock now but will be (back-order)",
    4: "Amazon offer shipping is delayed; see availabilityAmazonDelay",
}
SNAPSHOT_KEYS = (
    "manufacturer",
    "binding",
    "type",
    "model",
    "numberOfItems",
    "packageQuantity",
    "itemTypeKeyword",
    "style",
    "pattern",
    "websiteDisplayGroup",
    "websiteDisplayGroupName",
    "salesRankDisplayGroup",
    "availabilityAmazonDelay",
    "launchpad",
    "isAdultProduct",
    "urlSlug",
    "productGroup",
    "partNumber",
    "edition",
    "format",
    "packageHeight",
    "packageLength",
    "packageWidth",
    "packageWeight",
    "packageQuantity",
    "itemHeight",
    "itemLength",
    "itemWidth",
    "itemWeight",
)

POINT_DEFAULTS = {
    "category_id": None,
    "category_name": None,
    "category_resolution": "not_applicable",
    "value_num": None,
    "value_text": None,
    "value_missing_reason": None,
    "sentinel_raw": None,
    "currency": None,
    "price_type": None,
    "price_cents": None,
    "shipping_cents": None,
    "price_basis": None,
    "count_kind": None,
    "count_scope": None,
    "source_updated_at": None,
    "stock_qty": None,
    "offer_id": None,
    "seller_id": None,
    "offer_condition": None,
    "is_valid_measurement": 0,
}


@dataclass
class DecodeResult:
    asin: str | None = None
    rejected_reason: str | None = None
    points: list[dict] = field(default_factory=list)
    presence: list[dict] = field(default_factory=list)
    snapshot: dict | None = None
    variations: list[dict] = field(default_factory=list)
    category_names: list[dict] = field(default_factory=list)


def _usable_category(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        else:
            return None
    text = str(value)
    if text in {BLANK_CATEGORY, "0", "-1", "-2"} or value <= 0:
        return None
    return text


def _category_names(product: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    tree = product.get("categoryTree") or []
    if isinstance(tree, list):
        for node in tree:
            if isinstance(node, dict) and "catId" in node and isinstance(node.get("name"), str):
                usable = _usable_category(node.get("catId"))
                if usable:
                    names[usable] = node["name"]
    return names


def _pairs(history: object) -> tuple[list[tuple[int, object]] | None, str | None]:
    if history is None:
        return None, "absent"
    if not isinstance(history, list):
        return None, "not_a_list"
    if len(history) == 0:
        return [], None
    if len(history) % 2 != 0:
        return None, "odd_length"
    out = []
    for index in range(0, len(history), 2):
        stamp = history[index]
        if isinstance(stamp, bool) or not isinstance(stamp, int):
            return None, "non_integer_time"
        out.append((stamp, history[index + 1]))
    return out, None


def _triplets(history: object) -> tuple[list[tuple[int, object, object]] | None, str | None]:
    if history is None:
        return None, "absent"
    if not isinstance(history, list):
        return None, "not_a_list"
    if len(history) == 0:
        return [], None
    if len(history) % 3 != 0:
        return None, "length_not_multiple_of_3"
    out = []
    for index in range(0, len(history), 3):
        stamp = history[index]
        if isinstance(stamp, bool) or not isinstance(stamp, int):
            return None, "non_integer_time"
        out.append((stamp, history[index + 1], history[index + 2]))
    return out, None


def make_point(identity: str, **kwargs) -> dict:
    row = dict(POINT_DEFAULTS)
    row.update(kwargs)
    for key in (
        "asin",
        "domain_id",
        "series_kind",
        "observed_at",
        "definition_variant",
        "source_field",
        "source_update_status",
        "source_update_reason",
    ):
        if row.get(key) is None:
            raise AmazonBsrError("decode_bug", f"observation missing {key}")
    conflict = {
        "asin": row["asin"],
        "domain_id": row["domain_id"],
        "series_kind": row["series_kind"],
        "category_id": row["category_id"] or "",
        "definition_variant": row["definition_variant"],
        "price_type": row["price_type"] or "",
        "offer_id": row["offer_id"] or "",
        "observed_at": row["observed_at"],
    }
    natural = dict(conflict)
    natural["identity"] = identity
    natural["shipping_cents"] = row["shipping_cents"]
    natural["stock_qty"] = row["stock_qty"]
    row["conflict_key"] = canonical_hash(conflict)
    row["natural_key"] = canonical_hash(natural)
    return row


def _reference_history(product: dict) -> tuple[list[tuple[int, object]] | None, str | None]:
    history = product.get("salesRankReferenceHistory")
    if history is None:
        return [], "absent"
    return _pairs(history)


def category_at(history: list[tuple[int, object]], keepa_time: int) -> tuple[str | None, str]:
    seen = False
    chosen: object = None
    for stamp, category in history:
        if stamp <= keepa_time:
            chosen = category
            seen = True
        else:
            break
    if not seen:
        return None, "unresolved_before_first_reference"
    usable = _usable_category(chosen)
    if usable is None:
        return None, "unresolved_sentinel_category"
    return usable, "resolved"


def _rank_bits(raw: object) -> dict:
    if raw is None:
        return {
            "value_num": None,
            "value_missing_reason": "null_value",
            "sentinel_raw": None,
            "is_valid_measurement": 0,
            "identity": "null",
            "value_text": None,
        }
    if isinstance(raw, bool) or not isinstance(raw, int):
        return {
            "value_num": None,
            "value_missing_reason": "non_integer",
            "sentinel_raw": None,
            "is_valid_measurement": 0,
            "identity": "non_integer",
            "value_text": None,
        }
    if raw == -1:
        return {
            "value_num": None,
            "value_missing_reason": "keepa_missing_sentinel",
            "sentinel_raw": -1,
            "is_valid_measurement": 0,
            "identity": "sentinel:-1",
            "value_text": None,
        }
    if raw <= 0:
        return {
            "value_num": None,
            "value_missing_reason": "nonpositive",
            "sentinel_raw": raw,
            "is_valid_measurement": 0,
            "identity": f"nonpositive:{raw}",
            "value_text": None,
        }
    return {
        "value_num": float(raw),
        "value_missing_reason": None,
        "sentinel_raw": None,
        "is_valid_measurement": 1,
        "identity": f"rank:{raw}",
        "value_text": None,
    }


def _count_bits(raw: object, identity_prefix: str) -> dict:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return {
            "value_num": None,
            "value_missing_reason": "non_integer" if raw is not None else "null_value",
            "sentinel_raw": None,
            "is_valid_measurement": 0,
            "identity": "bad_count",
        }
    if raw == -1:
        return {
            "value_num": None,
            "value_missing_reason": "keepa_missing_sentinel",
            "sentinel_raw": -1,
            "is_valid_measurement": 0,
            "identity": "sentinel:-1",
        }
    if raw < 0:
        return {
            "value_num": None,
            "value_missing_reason": "negative_count",
            "sentinel_raw": raw,
            "is_valid_measurement": 0,
            "identity": f"negative:{raw}",
        }
    return {
        "value_num": float(raw),
        "value_missing_reason": None,
        "sentinel_raw": None,
        "is_valid_measurement": 1,
        "identity": f"{identity_prefix}:{raw}",
    }


def _price_bits(raw: object) -> dict:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return {
            "price_cents": None,
            "value_num": None,
            "value_missing_reason": "non_integer" if raw is not None else "null_value",
            "sentinel_raw": None,
            "is_valid_measurement": 0,
            "identity": "bad_price",
        }
    if raw == -1:
        return {
            "price_cents": None,
            "value_num": None,
            "value_missing_reason": "keepa_missing_sentinel",
            "sentinel_raw": -1,
            "is_valid_measurement": 0,
            "identity": "sentinel:-1",
        }
    if raw == -2:
        return {
            "price_cents": None,
            "value_num": None,
            "value_missing_reason": "undetermined",
            "sentinel_raw": -2,
            "is_valid_measurement": 0,
            "identity": "sentinel:-2",
        }
    if raw < 0:
        return {
            "price_cents": None,
            "value_num": None,
            "value_missing_reason": "negative_price",
            "sentinel_raw": raw,
            "is_valid_measurement": 0,
            "identity": f"negative:{raw}",
        }
    return {
        "price_cents": raw,
        "value_num": raw / 100.0,
        "value_missing_reason": None,
        "sentinel_raw": None,
        "is_valid_measurement": 1,
        "identity": f"cents:{raw}",
    }


def _shipping_bits(raw: object) -> tuple[int | None, str | None]:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None, "shipping_non_integer"
    if raw == -1:
        return None, "shipping_unspecified_or_not_shippable"
    if raw == -2:
        return None, "shipping_undetermined"
    if raw < 0:
        return None, "shipping_negative"
    if raw == 0:
        return 0, "free_shipping"
    return raw, None


def _price_basis(index: int, name: str, observed_at: str) -> str:
    if index in LISTING_PRICE_INDEXES:
        if observed_at >= LANDING_PRICE_CUTOFF:
            return "lowest_landing_price_on_or_after_2026-02-23"
        return "lowest_listing_price_before_2026-02-23"
    if CSV_TYPES[index][1] == 3:
        return "price_and_shipping_stored_separately_not_summed"
    return f"as_documented_for_{name}"


def _update_iso(product: dict, field: str) -> str | None:
    raw = product.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    if field == "listedSince" and raw == 0:
        return None
    return keepa_minutes_to_utc(raw)


def decode_product(product: object, *, domain_id: int) -> DecodeResult:
    result = DecodeResult()
    if not isinstance(product, dict):
        result.rejected_reason = "product_not_object"
        return result
    if domain_id != 1:
        result.rejected_reason = "domain_not_enabled"
        return result
    asin = product.get("asin")
    if not isinstance(asin, str) or not asin:
        result.rejected_reason = "missing_asin"
        return result
    result.asin = asin
    declared = product.get("domainId")
    if declared is not None and declared != domain_id:
        result.rejected_reason = "domain_mismatch"
        return result
    names = _category_names(product)
    for category_id, name in sorted(names.items()):
        result.category_names.append({"category_id": category_id, "name": name})
    ref_history, ref_problem = _reference_history(product)
    result.presence.append(
        _presence(
            "salesRankReferenceHistory",
            present=0 if ref_problem == "absent" else 1,
            point_count=None if ref_history is None else len(ref_history),
            note=(
                "No salesRankReferenceHistory. csv[3] SALES points are not assigned to the "
                "current salesRankReference, because a later category change would look like rank movement."
                if ref_problem == "absent"
                else f"salesRankReferenceHistory not decoded ({ref_problem})."
            ),
        )
    )
    if ref_history:
        _decode_reference_points(result, product, asin, domain_id, ref_history)
    _decode_sales_ranks(result, product, asin, domain_id, names)
    _decode_csv(result, product, asin, domain_id, names, ref_history if ref_problem is None else None, ref_problem)
    _decode_reviews(result, product, asin, domain_id)
    _decode_monthly_sold(result, product, asin, domain_id)
    _decode_parent_history(result, product, asin, domain_id)
    _decode_offers(result, product, asin, domain_id)
    result.snapshot = _snapshot(product, asin, domain_id, names)
    _decode_variations(result, product, asin, domain_id)
    return result


def _presence(source_field: str, *, present: int, point_count: int | None, note: str) -> dict:
    return {
        "source_field": source_field,
        "present": present,
        "point_count": point_count,
        "note": note,
    }


def _common_update(product: dict, field: str, status: str, reason: str) -> dict:
    return {
        "source_updated_at": _update_iso(product, field),
        "source_update_status": status if _update_iso(product, field) or status != "observed" else "update_time_not_in_payload",
        "source_update_reason": reason,
    }


def _decode_reference_points(result: DecodeResult, product: dict, asin: str, domain_id: int, history: list) -> None:
    update = _common_update(product, "lastUpdate", "observed", "Reference category history point. This is not a sales rank.")
    for stamp, category in history:
        observed = keepa_minutes_to_utc(stamp)
        if observed is None:
            continue
        usable = _usable_category(category)
        result.points.append(
            make_point(
                f"reference:{category}",
                asin=asin,
                domain_id=domain_id,
                series_kind="sales_rank_reference",
                observed_at=observed,
                keepa_time_minutes=stamp,
                definition_variant="keepa_salesRankReferenceHistory_v1",
                source_field="salesRankReferenceHistory",
                category_resolution="resolved" if usable else "unresolved_sentinel_category",
                value_text=str(category),
                value_missing_reason=None if usable else "sentinel_category",
                is_valid_measurement=0,
                **update,
            )
        )


def _decode_sales_ranks(result: DecodeResult, product: dict, asin: str, domain_id: int, names: dict[str, str]) -> None:
    raw = product.get("salesRanks")
    if raw is None:
        result.presence.append(
            _presence(
                "salesRanks",
                present=0,
                point_count=0,
                note="salesRanks absent. No per-category rank was invented from csv[3].",
            )
        )
        return
    if not isinstance(raw, dict):
        result.presence.append(_presence("salesRanks", present=0, point_count=None, note="salesRanks was not an object."))
        return
    if len(raw) == 0:
        result.presence.append(
            _presence("salesRanks", present=1, point_count=0, note="salesRanks was an empty object. That is not rank 0.")
        )
        return
    update = _common_update(product, "lastUpdate", "observed", SALES_CHANGE_ONLY)
    total = 0
    for key in raw:
        history, problem = _pairs(raw[key])
        field = f"salesRanks[{key}]"
        usable = _usable_category(int(key) if isinstance(key, str) and key.lstrip("-").isdigit() else key)
        if problem == "absent" or history is None:
            result.presence.append(_presence(field, present=0, point_count=None, note=f"salesRanks series unparsed ({problem})."))
            continue
        result.presence.append(
            _presence(
                field,
                present=1,
                point_count=len(history),
                note="Empty category history is not a zero rank." if not history else "Per-category sales rank. A change in another category is a different series.",
            )
        )
        if usable is None:
            continue
        for stamp, value in history:
            observed = keepa_minutes_to_utc(stamp)
            if observed is None:
                continue
            bits = _rank_bits(value)
            result.points.append(
                make_point(
                    bits["identity"],
                    asin=asin,
                    domain_id=domain_id,
                    series_kind="bsr_sales_ranks",
                    category_id=usable,
                    category_name=names.get(usable),
                    category_resolution="resolved",
                    observed_at=observed,
                    keepa_time_minutes=stamp,
                    definition_variant="keepa_salesranks_category_v1",
                    source_field=field,
                    value_num=bits["value_num"],
                    value_text=bits["value_text"],
                    value_missing_reason=bits["value_missing_reason"],
                    sentinel_raw=bits["sentinel_raw"],
                    is_valid_measurement=bits["is_valid_measurement"],
                    **update,
                )
            )
            total += 1
    if total == 0 and raw:
        result.presence.append(
            _presence(
                "salesRanks",
                present=1,
                point_count=0,
                note="salesRanks keys were present but no usable category/time point was decoded.",
            )
        )


def _decode_csv(result, product, asin, domain_id, names, ref_history, ref_problem) -> None:
    csv = product.get("csv")
    if csv is None:
        result.presence.append(
            _presence(
                "csv",
                present=0,
                point_count=0,
                note="csv absent. Rating and sales history were not filled with zeros.",
            )
        )
        return
    if not isinstance(csv, list):
        result.presence.append(_presence("csv", present=0, point_count=None, note="csv was not an array."))
        return
    for index, slot in enumerate(csv):
        spec = CSV_TYPES.get(index)
        if spec is None:
            if slot is not None:
                result.presence.append(
                    _presence(
                        f"csv[{index}]",
                        present=1,
                        point_count=len(slot) if isinstance(slot, list) else None,
                        note=(
                            "Unknown csv index. Keepa may add types without announcement. "
                            "This slot was not decoded as a price, rank, rating, or count. The raw payload still holds it."
                        ),
                    )
                )
            continue
        name, step, family = spec
        if family == "ebay":
            result.presence.append(
                _presence(
                    f"csv[{index}]",
                    present=0 if slot is None else 1,
                    point_count=len(slot) if isinstance(slot, list) else None,
                    note=(
                        f"csv[{index}] {name} is eBay, not Amazon. Keepa warns eBay listings are often mismatched. "
                        "No Amazon price or rank observation was created. The raw payload still holds the array."
                    ),
                )
            )
            continue
        if slot is None:
            note = _null_csv_note(index, name, family)
            if note:
                result.presence.append(_presence(f"csv[{index}]", present=0, point_count=0, note=note))
            continue
        parsed, problem = _triplets(slot) if step == 3 else _pairs(slot)
        if parsed is None:
            result.presence.append(
                _presence(
                    f"csv[{index}]",
                    present=0,
                    point_count=None,
                    note=f"csv[{index}] {name} shape {problem}. Points were not guessed.",
                )
            )
            continue
        result.presence.append(
            _presence(
                f"csv[{index}]",
                present=1,
                point_count=len(parsed),
                note=_present_csv_note(index, name, family, len(parsed)),
            )
        )
        if family == "retired":
            continue
        for offset, item in enumerate(parsed):
            _emit_csv_point(
                result,
                product,
                asin,
                domain_id,
                names,
                ref_history,
                ref_problem,
                index,
                name,
                family,
                item,
                is_last=offset == len(parsed) - 1,
            )
    for index in (3, 16, 17):
        if index >= len(csv):
            name, _step, family = CSV_TYPES[index]
            result.presence.append(
                _presence(
                    f"csv[{index}]",
                    present=0,
                    point_count=0,
                    note=_null_csv_note(index, name, family) or "csv slot was not in the array",
                )
            )


def _null_csv_note(index: int, name: str, family: str) -> str | None:
    if index == 3:
        return "csv[3] SALES is null. No sales rank was invented. Variation items often have no individual sales rank."
    if index == 16:
        return (
            "csv[16] RATING is null. This is not zero stars. Rating history is included only when the "
            "request used offers or rating=1, and it is not a full history from first listing."
        )
    if index == 17:
        return (
            "csv[17] COUNT_REVIEWS is null. The documented field is rating count, not written reviews, "
            "and null is not a review count of zero."
        )
    if family == "retired":
        return "csv[31] RENT is retired and is never populated. Null does not mean a rental price of zero."
    return None


def _present_csv_note(index: int, name: str, family: str, count: int) -> str:
    if count == 0:
        return f"csv[{index}] {name} was an empty list. That is not a zero measurement."
    if index == 16:
        return "csv[16] RATING values are integers 0-50 (45 = 4.5 stars). -1 is missing, not zero stars."
    if index == 17:
        return RATING_COUNT_REASON
    if family == "retired":
        return "csv[31] RENT is retired. Any payload in this slot was not interpreted as a price."
    if family == "trade_in":
        return "TRADE_IN is not an Amazon retail price and is not used as one."
    if family == "meta":
        return (
            "EXTRA_INFO_UPDATES records when offers-related fields were fetched. "
            "The absolute value is an offer-fetch count, not a price or rank. Negative means not all offers were fetched."
        )
    return f"Decoded csv[{index}] {name} with the documented entry width. -1 is missing, not a measurement."


def _emit_csv_point(result, product, asin, domain_id, names, ref_history, ref_problem, index, name, family, item, is_last: bool) -> None:
    stamp = item[0]
    observed = keepa_minutes_to_utc(stamp)
    if observed is None:
        return
    if family == "sales":
        _emit_csv_sales(result, product, asin, domain_id, names, ref_history, ref_problem, stamp, observed, item[1])
        return
    if family == "rating":
        _emit_rating(result, product, asin, domain_id, stamp, observed, item[1])
        return
    if family == "rating_count":
        _emit_csv_rating_count(result, product, asin, domain_id, stamp, observed, item[1])
        return
    if family == "offer_count":
        _emit_offer_count(result, product, asin, domain_id, index, name, stamp, observed, item[1])
        return
    if family == "meta":
        _emit_extra_info(result, product, asin, domain_id, stamp, observed, item[1])
        return
    if family == "trade_in":
        bits = _price_bits(item[1])
        result.points.append(
            make_point(
                "trade_in:" + bits["identity"],
                asin=asin,
                domain_id=domain_id,
                series_kind="trade_in",
                observed_at=observed,
                keepa_time_minutes=stamp,
                definition_variant="keepa_csv30_TRADE_IN_v1",
                source_field="csv[30]",
                price_type="TRADE_IN",
                currency="USD",
                price_cents=bits["price_cents"],
                value_num=None,
                value_missing_reason="trade_in_not_retail_price",
                sentinel_raw=bits["sentinel_raw"] if bits["price_cents"] is None else bits["price_cents"],
                is_valid_measurement=0,
                price_basis="trade_in_not_retail_price",
                **_common_update(product, "lastPriceChange", "observed", "Trade-in is not an Amazon retail price."),
            )
        )
        return
    if family == "price":
        _emit_price(result, product, asin, domain_id, index, name, stamp, observed, item, is_last)


def _emit_csv_sales(result, product, asin, domain_id, names, ref_history, ref_problem, stamp, observed, raw) -> None:
    bits = _rank_bits(raw)
    if ref_problem == "absent" or ref_history == []:
        resolution = "unresolved_no_reference_history"
        category_id = None
    elif ref_history is None or ref_problem not in (None, "absent"):
        resolution = "unresolved_history_unparsed"
        category_id = None
    else:
        category_id, resolution = category_at(ref_history, stamp)
    valid = bits["is_valid_measurement"] == 1 and resolution == "resolved" and category_id is not None
    identity = bits["identity"] if valid else f"withheld:{bits['identity']}"
    value_num = bits["value_num"] if valid else None
    value_text = None if valid or bits["value_num"] is None else f"raw_rank:{int(bits['value_num'])}"
    if not valid and bits["is_valid_measurement"] == 1:
        value_text = f"raw_rank:{int(bits['value_num'])};category:{resolution}"
    result.points.append(
        make_point(
            identity,
            asin=asin,
            domain_id=domain_id,
            series_kind="bsr_csv_sales",
            category_id=category_id,
            category_name=names.get(category_id) if category_id else None,
            category_resolution=resolution,
            observed_at=observed,
            keepa_time_minutes=stamp,
            definition_variant="keepa_csv3_sales_with_reference_history_v1",
            source_field="csv[3]",
            value_num=value_num,
            value_text=value_text,
            value_missing_reason=bits["value_missing_reason"] if bits["is_valid_measurement"] == 0 else None,
            sentinel_raw=bits["sentinel_raw"],
            is_valid_measurement=1 if valid else 0,
            **_common_update(
                product,
                "lastUpdate",
                "observed",
                SALES_CHANGE_ONLY
                + " csv[3] is the reference-category rank, matched with salesRankReferenceHistory at this timestamp.",
            ),
        )
    )


def _emit_rating(result, product, asin, domain_id, stamp, observed, raw) -> None:
    status = "observed"
    reason = (
        "csv[16] RATING is an integer from 0 to 50 (45 = 4.5 stars). It is not a written review count. "
        "History starts when Keepa collected it, not at listing."
    )
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0 or raw > 50:
        if raw == -1:
            bits = {
                "value_num": None,
                "value_missing_reason": "keepa_missing_sentinel",
                "sentinel_raw": -1,
                "is_valid_measurement": 0,
                "identity": "sentinel:-1",
                "value_text": None,
            }
        else:
            bits = {
                "value_num": None,
                "value_missing_reason": "rating_outside_0_50",
                "sentinel_raw": raw if isinstance(raw, int) and not isinstance(raw, bool) else None,
                "is_valid_measurement": 0,
                "identity": "unscaled",
                "value_text": None,
            }
            reason = "Rating outside 0-50 was not divided by 10."
    else:
        bits = {
            "value_num": raw / 10.0,
            "value_missing_reason": None,
            "sentinel_raw": None,
            "is_valid_measurement": 1,
            "identity": f"rating_raw:{raw}",
            "value_text": f"keepa_raw={raw}",
        }
    result.points.append(
        make_point(
            bits["identity"],
            asin=asin,
            domain_id=domain_id,
            series_kind="rating",
            observed_at=observed,
            keepa_time_minutes=stamp,
            definition_variant="keepa_csv16_rating_stars_v1",
            source_field="csv[16]",
            count_scope="non_variation",
            value_num=bits["value_num"],
            value_text=bits["value_text"],
            value_missing_reason=bits["value_missing_reason"],
            sentinel_raw=bits["sentinel_raw"],
            is_valid_measurement=bits["is_valid_measurement"],
            **_common_update(product, "lastRatingUpdate", status, reason),
        )
    )


def _emit_csv_rating_count(result, product, asin, domain_id, stamp, observed, raw) -> None:
    bits = _count_bits(raw, "rating_count")
    result.points.append(
        make_point(
            bits["identity"],
            asin=asin,
            domain_id=domain_id,
            series_kind="rating_count",
            observed_at=observed,
            keepa_time_minutes=stamp,
            definition_variant="keepa_csv17_COUNT_REVIEWS_rating_count_v1",
            source_field="csv[17]",
            count_kind="rating_count",
            count_scope="non_variation",
            value_num=bits["value_num"],
            value_missing_reason=bits["value_missing_reason"],
            sentinel_raw=bits["sentinel_raw"],
            is_valid_measurement=bits["is_valid_measurement"],
            **_common_update(product, "lastRatingUpdate", "observed", RATING_COUNT_REASON),
        )
    )


def _emit_offer_count(result, product, asin, domain_id, index, name, stamp, observed, raw) -> None:
    bits = _count_bits(raw, "offer_count")
    result.points.append(
        make_point(
            bits["identity"],
            asin=asin,
            domain_id=domain_id,
            series_kind="offer_count",
            observed_at=observed,
            keepa_time_minutes=stamp,
            definition_variant=f"keepa_csv{index}_{name}_v1",
            source_field=f"csv[{index}]",
            count_kind="offer_count",
            count_scope="marketplace",
            value_num=bits["value_num"],
            value_missing_reason=bits["value_missing_reason"],
            sentinel_raw=bits["sentinel_raw"],
            is_valid_measurement=bits["is_valid_measurement"],
            **_common_update(product, "lastUpdate", "observed", f"csv[{index}] {name} is an offer count, not unit sales."),
        )
    )


def _emit_extra_info(result, product, asin, domain_id, stamp, observed, raw) -> None:
    sentinel = raw if isinstance(raw, int) and not isinstance(raw, bool) else None
    result.points.append(
        make_point(
            f"extra_info:{sentinel}",
            asin=asin,
            domain_id=domain_id,
            series_kind="csv_extra_info_updates",
            observed_at=observed,
            keepa_time_minutes=stamp,
            definition_variant="keepa_csv15_extra_info_updates_v1",
            source_field="csv[15]",
            value_num=None,
            sentinel_raw=sentinel,
            value_text=None if sentinel is None else f"raw:{sentinel}",
            value_missing_reason="offer_fetch_marker_not_a_measurement",
            is_valid_measurement=0,
            **_common_update(
                product,
                "lastUpdate",
                "observed",
                "EXTRA_INFO_UPDATES is an offer-fetch marker. Positive means all offers were fetched; negative means more remained.",
            ),
        )
    )


def _emit_price(result, product, asin, domain_id, index, name, stamp, observed, item, is_last: bool) -> None:
    raw_price = item[1]
    shipping = item[2] if len(item) == 3 else None
    bits = _price_bits(raw_price)
    ship_cents, ship_note = (None, None) if shipping is None else _shipping_bits(shipping)
    reason = "Price is integer cents for domain 1 (USD). -1 means no offer in that interval, not a price of -1."
    valid = bits["is_valid_measurement"]
    if index == 8 and is_last and raw_price == -1:
        reason = (
            "Lightning Deal history: the last -1 can be the deal end (a future time) or an announced start, "
            "not a selling price. It was not stored as a price."
        )
        valid = 0
    if ship_note and valid:
        reason = reason + " " + ship_note + ". Shipping cents are not added into the price."
    result.points.append(
        make_point(
            bits["identity"] + (f":ship:{ship_cents}" if ship_cents is not None else ""),
            asin=asin,
            domain_id=domain_id,
            series_kind="price",
            observed_at=observed,
            keepa_time_minutes=stamp,
            definition_variant=f"keepa_csv{index}_{name}_v1",
            source_field=f"csv[{index}]",
            price_type=name,
            currency="USD",
            price_cents=bits["price_cents"] if valid else None,
            shipping_cents=ship_cents if valid else None,
            value_num=bits["value_num"] if valid else None,
            value_missing_reason=bits["value_missing_reason"],
            sentinel_raw=bits["sentinel_raw"],
            price_basis=_price_basis(index, name, observed),
            is_valid_measurement=valid,
            **_common_update(product, "lastPriceChange", "observed", reason),
        )
    )


def _decode_reviews(result: DecodeResult, product: dict, asin: str, domain_id: int) -> None:
    reviews = product.get("reviews")
    if not isinstance(reviews, dict):
        result.presence.append(
            _presence(
                "reviews",
                present=0,
                point_count=0,
                note=(
                    "reviews object absent. It is only returned when the rating parameter was used. "
                    "Absence is not a zero written-review count. csv rating fields, if present, are separate."
                ),
            )
        )
        return
    last = reviews.get("lastUpdate")
    updated = keepa_minutes_to_utc(last) if isinstance(last, int) and not isinstance(last, bool) and last >= 0 else None
    for key, series, kind, variant, reason, status in (
        (
            "ratingCount",
            "rating_count",
            "rating_count",
            "keepa_reviews_ratingCount_variation_v1",
            RATING_COUNT_STALE_REASON,
            "documented_stale",
        ),
        (
            "reviewCount",
            "written_review_count",
            "written_review_count",
            "keepa_reviews_reviewCount_written_variation_v1",
            WRITTEN_REVIEW_REASON,
            "observed",
        ),
    ):
        history, problem = _pairs(reviews.get(key)) if key in reviews else (None, "absent")
        if key not in reviews or problem == "absent":
            result.presence.append(
                _presence(f"reviews.{key}", present=0, point_count=0, note=f"reviews.{key} absent. Not filled with zero. {reason}")
            )
            continue
        if history is None:
            result.presence.append(_presence(f"reviews.{key}", present=0, point_count=None, note=f"reviews.{key} shape {problem}."))
            continue
        result.presence.append(_presence(f"reviews.{key}", present=1, point_count=len(history), note=reason))
        for stamp, raw in history:
            observed = keepa_minutes_to_utc(stamp)
            if observed is None:
                continue
            bits = _count_bits(raw, kind)
            result.points.append(
                make_point(
                    bits["identity"],
                    asin=asin,
                    domain_id=domain_id,
                    series_kind=series,
                    observed_at=observed,
                    keepa_time_minutes=stamp,
                    definition_variant=variant,
                    source_field=f"reviews.{key}",
                    count_kind=kind,
                    count_scope="variation",
                    value_num=bits["value_num"],
                    value_missing_reason=bits["value_missing_reason"],
                    sentinel_raw=bits["sentinel_raw"],
                    is_valid_measurement=bits["is_valid_measurement"],
                    source_updated_at=updated,
                    source_update_status=status if updated else "update_time_not_in_payload",
                    source_update_reason=reason,
                )
            )


def _decode_monthly_sold(result, product, asin, domain_id) -> None:
    history, problem = _pairs(product.get("monthlySoldHistory")) if "monthlySoldHistory" in product else (None, "absent")
    if problem == "absent" or product.get("monthlySoldHistory") is None:
        result.presence.append(
            _presence(
                "monthlySoldHistory",
                present=0,
                point_count=0,
                note=(
                    "monthlySoldHistory absent. Amazon's bought-past-month figure is a bracket such as 10+ or 100+, "
                    "not exact units and not GMV. Most ASINs have no value. Nothing was filled in."
                ),
            )
        )
        return
    if history is None:
        result.presence.append(_presence("monthlySoldHistory", present=0, point_count=None, note=f"shape {problem}."))
        return
    result.presence.append(
        _presence(
            "monthlySoldHistory",
            present=1,
            point_count=len(history),
            note="Stored as a bracket floor, is_valid_measurement=0, and never as a sales or BSR metric.",
        )
    )
    update = _common_update(
        product,
        "lastSoldUpdate",
        "observed",
        "monthlySold is Amazon's bought-past-month bracket, variation specific, not exact sales and not GMV.",
    )
    for stamp, raw in history:
        observed = keepa_minutes_to_utc(stamp)
        if observed is None:
            continue
        number = raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else None
        result.points.append(
            make_point(
                f"monthly_sold_bracket:{number}",
                asin=asin,
                domain_id=domain_id,
                series_kind="monthly_sold_bracket",
                observed_at=observed,
                keepa_time_minutes=stamp,
                definition_variant="keepa_monthlySold_bracket_v1",
                source_field="monthlySoldHistory",
                value_num=float(number) if number is not None else None,
                value_missing_reason=None if number is not None else "unusable_bracket",
                is_valid_measurement=0,
                **update,
            )
        )


def _decode_parent_history(result, product, asin, domain_id) -> None:
    if product.get("parentAsinHistory") is None:
        result.presence.append(
            _presence(
                "parentAsinHistory",
                present=0,
                point_count=0,
                note=(
                    "parentAsinHistory absent. Keepa started tracking parent changes on 2024-03-18. "
                    "Absence does not prove the parent never changed. The current parent is the parentAsin field."
                ),
            )
        )
        return
    history, problem = _pairs(product.get("parentAsinHistory"))
    if history is None:
        result.presence.append(_presence("parentAsinHistory", present=0, point_count=None, note=f"shape {problem}."))
        return
    result.presence.append(
        _presence(
            "parentAsinHistory",
            present=1,
            point_count=len(history),
            note="Each timestamp is when that previous parent ceased to be valid. The current parent is not copied into this history.",
        )
    )
    for stamp, previous in history:
        observed = keepa_minutes_to_utc(stamp)
        if observed is None or not isinstance(previous, str):
            continue
        result.points.append(
            make_point(
                f"parent:{previous}",
                asin=asin,
                domain_id=domain_id,
                series_kind="parent_asin_history",
                observed_at=observed,
                keepa_time_minutes=stamp,
                definition_variant="keepa_parentAsinHistory_v1",
                source_field="parentAsinHistory",
                value_text=previous,
                is_valid_measurement=0,
                value_missing_reason="parent_change_not_a_rank",
                **_common_update(product, "lastUpdate", "observed", "Previous parent ASIN. Not a rank and not the current parent."),
            )
        )


def _decode_offers(result, product, asin, domain_id) -> None:
    offers = product.get("offers")
    if not isinstance(offers, list):
        result.presence.append(
            _presence(
                "offers",
                present=0,
                point_count=0,
                note="offers absent. Offer prices and stock were not manufactured. Stock requires the stock parameter and is still not guaranteed.",
            )
        )
        return
    result.presence.append(_presence("offers", present=1, point_count=len(offers), note="Marketplace offers included in this payload."))
    any_stock = False
    for offer_index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            continue
        offer_id = str(offer.get("offerId")) if offer.get("offerId") is not None else None
        seller = offer.get("sellerId") if isinstance(offer.get("sellerId"), str) else None
        condition = offer.get("condition") if isinstance(offer.get("condition"), int) and not isinstance(offer.get("condition"), bool) else None
        parsed, problem = _triplets(offer.get("offerCSV")) if offer.get("offerCSV") is not None else (None, "absent")
        if parsed is None and problem != "absent":
            result.presence.append(
                _presence(f"offers[{offer_index}].offerCSV", present=0, point_count=None, note=f"offerCSV shape {problem}.")
            )
        elif parsed is not None:
            for stamp, price, shipping in parsed:
                observed = keepa_minutes_to_utc(stamp)
                if observed is None:
                    continue
                bits = _price_bits(price)
                ship_cents, ship_note = _shipping_bits(shipping)
                valid = bits["is_valid_measurement"]
                reason = "offerCSV triplet is Keepa time, price cents, shipping cents. -2 means undetermined. Shipping -1 means unspecified or not shippable. Shipping 0 is free. Shipping is not added into the price."
                if ship_note:
                    reason = reason + " " + ship_note + "."
                last_seen = offer.get("lastSeen")
                source_updated = keepa_minutes_to_utc(last_seen) if isinstance(last_seen, int) and not isinstance(last_seen, bool) and last_seen >= 0 else None
                result.points.append(
                    make_point(
                        bits["identity"] + (f":ship:{ship_cents}" if ship_cents is not None else ""),
                        asin=asin,
                        domain_id=domain_id,
                        series_kind="offer_price",
                        observed_at=observed,
                        keepa_time_minutes=stamp,
                        definition_variant="keepa_offerCSV_v1",
                        source_field="offers.offerCSV",
                        price_type="OFFER",
                        currency="USD",
                        price_cents=bits["price_cents"] if valid else None,
                        shipping_cents=ship_cents if valid else None,
                        value_num=bits["value_num"] if valid else None,
                        value_missing_reason=bits["value_missing_reason"],
                        sentinel_raw=bits["sentinel_raw"],
                        price_basis="offer_price_and_shipping_separate",
                        offer_id=offer_id,
                        seller_id=seller,
                        offer_condition=condition,
                        is_valid_measurement=valid,
                        source_updated_at=source_updated,
                        source_update_status="observed" if source_updated else "update_time_not_in_payload",
                        source_update_reason=reason,
                    )
                )
        stock, stock_problem = _pairs(offer.get("stockCSV")) if offer.get("stockCSV") is not None else (None, "absent")
        if stock_problem == "absent":
            continue
        any_stock = True
        if stock is None:
            result.presence.append(
                _presence(f"offers[{offer_index}].stockCSV", present=0, point_count=None, note=f"stockCSV shape {stock_problem}.")
            )
            continue
        last_stock = offer.get("lastStockUpdate")
        stock_updated = keepa_minutes_to_utc(last_stock) if isinstance(last_stock, int) and not isinstance(last_stock, bool) and last_stock >= 0 else None
        for stamp, raw in stock:
            observed = keepa_minutes_to_utc(stamp)
            if observed is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                result.points.append(
                    make_point(
                        f"bad_stock:{raw}",
                        asin=asin,
                        domain_id=domain_id,
                        series_kind="offer_stock",
                        observed_at=observed,
                        keepa_time_minutes=stamp,
                        definition_variant="keepa_offer_stockcsv_v1",
                        source_field="offers.stockCSV",
                        offer_id=offer_id,
                        seller_id=seller,
                        offer_condition=condition,
                        value_missing_reason="unusable_stock",
                        sentinel_raw=raw if isinstance(raw, int) and not isinstance(raw, bool) else None,
                        is_valid_measurement=0,
                        source_updated_at=stock_updated,
                        source_update_status="observed" if stock_updated else "update_time_not_in_payload",
                        source_update_reason=STOCK_REASON,
                    )
                )
                continue
            result.points.append(
                make_point(
                    f"stock:{raw}",
                    asin=asin,
                    domain_id=domain_id,
                    series_kind="offer_stock",
                    observed_at=observed,
                    keepa_time_minutes=stamp,
                    definition_variant="keepa_offer_stockcsv_v1",
                    source_field="offers.stockCSV",
                    offer_id=offer_id,
                    seller_id=seller,
                    offer_condition=condition,
                    stock_qty=raw,
                    value_num=float(raw),
                    is_valid_measurement=1,
                    source_updated_at=stock_updated,
                    source_update_status="observed" if stock_updated else "update_time_not_in_payload",
                    source_update_reason=STOCK_REASON,
                )
            )
    if not any_stock:
        result.presence.append(
            _presence(
                "offers.stockCSV",
                present=0,
                point_count=0,
                note="No offer included stockCSV. Stock was not filled with zero. availabilityAmazon, if present, is only a current Amazon-offer code on the snapshot.",
            )
        )


def _snapshot(product: dict, asin: str, domain_id: int, names: dict[str, str]) -> dict:
    categories = []
    for item in product.get("categories") or []:
        usable = _usable_category(item)
        if usable:
            categories.append(usable)
    attributes = {}
    for key in SNAPSHOT_KEYS:
        if key in product and product.get(key) is not None:
            attributes[key] = product.get(key)
    notes = []
    product_type = product.get("productType") if isinstance(product.get("productType"), int) and not isinstance(product.get("productType"), bool) else None
    if product_type == 5:
        notes.append("productType 5 VARIATION_PARENT. variations is the child list. Child ASINs usually do not have their own sales rank.")
    if product_type == 4:
        notes.append("productType 4 INVALID. Keepa says no current data is available. Points in this payload are still stored as received.")
    availability = product.get("availabilityAmazon")
    if isinstance(availability, int) and not isinstance(availability, bool):
        note = AVAILABILITY_NOTES.get(availability, "undocumented availabilityAmazon code")
        notes.append(f"availabilityAmazon={availability}: {note}. This is a current code, not a stock history.")
        attributes["availabilityAmazon"] = availability
    else:
        availability = None
        notes.append("availabilityAmazon absent. No stock history was created from it.")
    listed_raw = product.get("listedSince") if isinstance(product.get("listedSince"), int) and not isinstance(product.get("listedSince"), bool) else None
    listed_at = None
    if listed_raw not in (None, 0, -1) and listed_raw > 0:
        listed_at = keepa_minutes_to_utc(listed_raw)
    elif listed_raw in (0, -1):
        notes.append("listedSince is 0 or -1, which Keepa documents as not available. It was not converted to 2011-01-01.")
    parent = product.get("parentAsin") if isinstance(product.get("parentAsin"), str) else None
    return {
        "asin": asin,
        "domain_id": domain_id,
        "product_type": product_type,
        "title": product.get("title") if isinstance(product.get("title"), str) else None,
        "brand": product.get("brand") if isinstance(product.get("brand"), str) else None,
        "color": product.get("color") if isinstance(product.get("color"), str) else None,
        "size": product.get("size") if isinstance(product.get("size"), str) else None,
        "material": product.get("material") if isinstance(product.get("material"), str) else None,
        "parent_asin": parent,
        "root_category_id": _usable_category(product.get("rootCategory")),
        "category_ids_json": categories,
        "attributes_json": attributes,
        "decode_notes_json": notes,
        "listed_since_raw": listed_raw,
        "listed_since_at": listed_at,
        "tracking_since_at": _update_iso(product, "trackingSince"),
        "last_update_at": _update_iso(product, "lastUpdate"),
        "last_rating_update_at": _update_iso(product, "lastRatingUpdate"),
        "last_stock_update_at": _update_iso(product, "lastStockUpdate"),
        "availability_amazon": availability,
        "observed_at": _update_iso(product, "lastUpdate"),
        "category_names": names,
    }


def _decode_variations(result: DecodeResult, product: dict, asin: str, domain_id: int) -> None:
    variations = product.get("variations")
    if not isinstance(variations, list):
        result.presence.append(
            _presence(
                "variations",
                present=0,
                point_count=0,
                note="variations absent. Children were not invented, and this does not add ASINs to the mapping pool.",
            )
        )
    else:
        result.presence.append(
            _presence(
                "variations",
                present=1,
                point_count=len(variations),
                note="Live variations observed on this payload. They are not automatic mapping-pool members.",
            )
        )
        for child in variations:
            if not isinstance(child, dict) or not isinstance(child.get("asin"), str):
                continue
            attrs = child.get("attributes") if isinstance(child.get("attributes"), list) else []
            result.variations.append(
                {
                    "domain_id": domain_id,
                    "parent_asin": asin,
                    "child_asin": child["asin"],
                    "attributes_json": attrs,
                    "image_filename": child.get("image") if isinstance(child.get("image"), str) else None,
                    "variation_scope": "live_variation",
                    "natural_identity": canonical_hash(
                        {"parent": asin, "child": child["asin"], "attributes": attrs, "scope": "live_variation"}
                    ),
                }
            )
    historical = product.get("historicalVariations")
    if not isinstance(historical, list):
        result.presence.append(
            _presence(
                "historicalVariations",
                present=0,
                point_count=0,
                note="historicalVariations absent unless historical-variations=1 was requested. Absence is not an empty variation set.",
            )
        )
        return
    result.presence.append(
        _presence(
            "historicalVariations",
            present=1,
            point_count=len(historical),
            note="Historical or out-of-stock variation ASINs. No attributes were invented for them.",
        )
    )
    for child_asin in historical:
        if not isinstance(child_asin, str):
            continue
        result.variations.append(
            {
                "domain_id": domain_id,
                "parent_asin": asin,
                "child_asin": child_asin,
                "attributes_json": [],
                "image_filename": None,
                "variation_scope": "historical_or_oos",
                "natural_identity": canonical_hash(
                    {"parent": asin, "child": child_asin, "scope": "historical_or_oos"}
                ),
            }
        )
