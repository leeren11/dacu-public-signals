"""US ASIN pool rules for the four frozen sku clusters.

The pool may be empty. Empty is needs_input, not a fabricated sample.
B0EXAMPL… identifiers are reserved for unit tests and are rejected on the
production import path.
"""

from __future__ import annotations

import json
import re

from amazon_bsr.errors import AmazonBsrError

DOMAIN_US = 1
POOL_MIN = 3
POOL_MAX = 5
EXAMPLE_PREFIX = "B0EXAMPL"
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{3,80}$")
POOL_NOTE = (
    "建议每组 3-5 个真实 US ASIN（domain=1）。0 个是 needs_input，允许。"
    "禁止把示例 ASIN 写入正式库。属性不能从相邻 ASIN 或组名里猜。"
)

TARGET_GROUPS: list[dict] = [
    {
        "sku_cluster": "holiday press-on nails",
        "display_zh": "节日甲片",
        "policy": {
            "product_form": {"required": True, "allow": ["press-on", "press_on"]},
            "theme": {"required": True, "non_empty_string": True},
            "forbid_keys": ["pendant_facet", "jewelry_form", "pack_count", "style_facet"],
        },
    },
    {
        "sku_cluster": "opal/birthstone/initial pendant (ready-stock)",
        "display_zh": "现货欧泊/字母吊坠",
        "policy": {
            "pendant_facet": {
                "required": True,
                "allow": ["opal", "birthstone", "initial"],
            },
            "additional_facets": {"allow_nonempty_only_with": "multi_facet_reason"},
            "forbid_combined_facet_blob": True,
            "forbid_keys": ["product_form", "pack_count", "jewelry_form", "style_facet"],
        },
    },
    {
        "sku_cluster": "friendship/beaded charm bracelet",
        "display_zh": "友谊串珠手链",
        "policy": {
            "jewelry_form": {"required": True, "allow": ["bracelet"]},
            "style_facet": {
                "required": True,
                "allow": ["friendship", "beaded", "charm"],
            },
            "additional_style_facets": {"allow_nonempty_only_with": "multi_style_reason"},
            "forbid_keys": ["pendant_facet", "pack_count", "product_form"],
        },
    },
    {
        "sku_cluster": "soft squishy multipack",
        "display_zh": "squishy 多件装",
        "policy": {
            "product_form": {"required": True, "allow": ["squishy"]},
            "pack_count": {"required": True, "int_min": 2},
            "forbid_keys": ["pendant_facet", "jewelry_form", "style_facet", "theme"],
        },
    },
]

GROUP_BY_SKU = {row["sku_cluster"]: row for row in TARGET_GROUPS}


def pool_status_for(count: int, low: int = POOL_MIN, high: int = POOL_MAX) -> str:
    if count <= 0:
        return "needs_input"
    if count < low:
        return "below_recommended"
    if count > high:
        return "above_recommended"
    return "within_recommended"


def policy_json(group: dict) -> str:
    return json.dumps(group["policy"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_example_asin(asin: str) -> bool:
    return asin.startswith(EXAMPLE_PREFIX)


def check_asin(asin: object, *, allow_example: bool) -> str:
    if not isinstance(asin, str) or not ASIN_RE.fullmatch(asin):
        raise AmazonBsrError("bad_asin", "ASIN must be 10 uppercase letters or digits; no placeholders")
    if is_example_asin(asin) and not allow_example:
        raise AmazonBsrError(
            "example_asin_refused",
            f"{asin} is reserved for tests. Production imports need a real US ASIN.",
        )
    return asin


def _reason(text: object, field: str) -> str:
    if not isinstance(text, str) or len(text.strip()) < 12:
        raise AmazonBsrError("reason_required", f"{field} needs at least 12 characters of operator text")
    return text.strip()


def _as_string_list(value: object, field: str, allowed: set[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AmazonBsrError("bad_attributes", f"{field} must be a list")
    out = []
    for item in value:
        if not isinstance(item, str) or item not in allowed:
            raise AmazonBsrError("bad_attributes", f"{field} contains a value outside {sorted(allowed)}")
        out.append(item)
    return out


def validate_attributes(sku: str, attributes: dict, item: dict) -> str | None:
    group = GROUP_BY_SKU.get(sku)
    if group is None:
        raise AmazonBsrError("unknown_sku_cluster", f"not one of the four initial groups: {sku}")
    if not isinstance(attributes, dict):
        raise AmazonBsrError("bad_attributes", "product_attributes must be an object")
    policy = group["policy"]
    allowed_keys = {
        key
        for key, rule in policy.items()
        if key not in {"forbid_keys", "forbid_combined_facet_blob"} and isinstance(rule, dict)
    }
    unknown = sorted(set(attributes) - allowed_keys)
    if unknown:
        raise AmazonBsrError(
            "attribute_mix",
            f"{sku} does not accept attributes {unknown}; do not copy fields from another group",
        )
    forbidden = set(policy.get("forbid_keys") or [])
    present_forbidden = sorted(forbidden.intersection(attributes))
    if present_forbidden:
        raise AmazonBsrError(
            "attribute_mix",
            f"{sku} must not carry attributes {present_forbidden}",
        )
    facet = None
    for key, rule in policy.items():
        if key in {"forbid_keys", "forbid_combined_facet_blob"}:
            continue
        if key in {"additional_facets", "additional_style_facets"}:
            allowed = set(policy["pendant_facet"]["allow"] if key == "additional_facets" else policy["style_facet"]["allow"])
            extras = _as_string_list(attributes.get(key), key, allowed)
            primary_key = "pendant_facet" if key == "additional_facets" else "style_facet"
            primary = attributes.get(primary_key)
            if primary in extras:
                raise AmazonBsrError("attribute_mix", f"{key} repeats the primary facet")
            if extras:
                _reason(item.get(rule["allow_nonempty_only_with"]), rule["allow_nonempty_only_with"])
            continue
        if not isinstance(rule, dict):
            continue
        value = attributes.get(key)
        if rule.get("required") and (value is None or value == "" or value == []):
            raise AmazonBsrError("attribute_required", f"{sku} requires product_attributes.{key}")
        if value is None:
            continue
        if "allow" in rule and value not in rule["allow"]:
            raise AmazonBsrError(
                "attribute_required",
                f"{sku} {key} must be one of {rule['allow']}",
            )
        if rule.get("non_empty_string"):
            if not isinstance(value, str) or not value.strip():
                raise AmazonBsrError("attribute_required", f"{sku} {key} must be a non-empty string")
        if "int_min" in rule:
            if isinstance(value, bool) or not isinstance(value, int) or value < rule["int_min"]:
                raise AmazonBsrError(
                    "attribute_required",
                    f"{sku} {key} must be an integer >= {rule['int_min']}",
                )
        if key == "pendant_facet":
            facet = value
    if policy.get("forbid_combined_facet_blob"):
        blob = json.dumps(attributes, ensure_ascii=False).lower()
        if "opal/birthstone" in blob or "opal/birthstone/initial" in blob:
            raise AmazonBsrError(
                "attribute_mix",
                "do not store a combined opal/birthstone/initial attribute; set pendant_facet to one value",
            )
        hits = [name for name in ("opal", "birthstone", "initial") if name in blob]
        # The primary facet is supposed to appear once. A second facet word inside
        # another string is the blind mix this group forbids.
        if facet and blob.count(facet) and len(hits) > 1 and not item.get("multi_facet_reason"):
            raise AmazonBsrError(
                "attribute_mix",
                "opal, birthstone, and initial must not be mixed in one attribute blob",
            )
    return facet


def validate_variation(role: str, asin: str, parent_asin: object, variation_attributes: object) -> str | None:
    if role not in {"parent", "child", "standalone"}:
        raise AmazonBsrError("bad_role", "role must be parent, child, or standalone")
    if variation_attributes is None:
        variation_attributes = []
    if not isinstance(variation_attributes, list):
        raise AmazonBsrError("bad_variation", "variation_attributes must be a list")
    cleaned = []
    for entry in variation_attributes:
        if not isinstance(entry, dict):
            raise AmazonBsrError("bad_variation", "each variation attribute needs dimension and value")
        dimension = entry.get("dimension")
        value = entry.get("value")
        if not isinstance(dimension, str) or not dimension.strip() or not isinstance(value, str) or not value.strip():
            raise AmazonBsrError("bad_variation", "variation dimension and value must be non-empty strings")
        cleaned.append({"dimension": dimension.strip(), "value": value.strip()})
    if role == "child":
        if parent_asin is None:
            raise AmazonBsrError("bad_variation", "a child mapping needs parent_asin")
        parent = check_asin(parent_asin, allow_example=True)
        if parent == asin:
            raise AmazonBsrError("bad_variation", "parent_asin must differ from the child ASIN")
        if not cleaned:
            raise AmazonBsrError("bad_variation", "a child mapping needs its own variation attributes")
        return parent
    if parent_asin not in (None, ""):
        raise AmazonBsrError("bad_variation", f"{role} mappings do not take parent_asin")
    if cleaned:
        raise AmazonBsrError("bad_variation", f"{role} mappings do not take variation_attributes; map the child itself")
    return None


def validate_category_ids(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise AmazonBsrError("category_required", "category_ids must list the Amazon node ids you actually checked")
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise AmazonBsrError("category_required", "category ids must be positive integers")
        if item == 9223372036854775807:
            raise AmazonBsrError("category_required", "Keepa's blank '?' category is not an inclusion category")
        out.append(str(item))
    if len(set(out)) != len(out):
        raise AmazonBsrError("category_required", "duplicate category id")
    return out


def check_version(version: object) -> str:
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise AmazonBsrError(
            "bad_mapping_version",
            "mapping_version must be 3-80 characters of letters, digits, dot, underscore, or hyphen",
        )
    if "example" in version.lower():
        raise AmazonBsrError("bad_mapping_version", "mapping_version must not be marked example")
    return version


def check_provenance(value: object) -> dict:
    if not isinstance(value, dict):
        raise AmazonBsrError("provenance_required", "provenance object is required")
    source = value.get("source")
    recorded_by = value.get("recorded_by")
    note = value.get("note")
    if not isinstance(source, str) or not source.strip():
        raise AmazonBsrError("provenance_required", "provenance.source is required")
    if not isinstance(recorded_by, str) or len(recorded_by.strip()) < 2 or recorded_by.strip().upper().startswith("FILL"):
        raise AmazonBsrError("provenance_required", "provenance.recorded_by must name the operator; FILL placeholders are refused")
    if not isinstance(note, str) or len(note.strip()) < 8:
        raise AmazonBsrError("provenance_required", "provenance.note must describe how the ASINs were chosen")
    license_note = value.get("license_note")
    if license_note is not None and not isinstance(license_note, str):
        raise AmazonBsrError("provenance_required", "provenance.license_note must be a string")
    return {
        "source": source.strip(),
        "recorded_by": recorded_by.strip(),
        "note": note.strip(),
        "license_note": (license_note or "").strip(),
    }
