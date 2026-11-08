"""Operator mapping of sku_cluster -> US ASIN. Versions are append-only."""

from __future__ import annotations

import json
from pathlib import Path

from amazon_bsr.db import refresh_pool_counts, require_migrated, transaction
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.policies import (
    GROUP_BY_SKU,
    TARGET_GROUPS,
    check_asin,
    check_provenance,
    check_version,
    validate_attributes,
    validate_category_ids,
    validate_variation,
    _reason,
)
from amazon_bsr.redact import canonical_hash
from amazon_bsr.timeutil import now_utc, parse_date


def template_document() -> dict:
    return {
        "_template": True,
        "_note": (
            "Empty pool template. Fill mapping_version, valid_from, and provenance, "
            "then delete _template. Add real 10-character US ASINs yourself. "
            "Do not use B0EXAMPL test ids. Leaving items empty keeps needs_input."
        ),
        "mapping_version": "",
        "domain_id": 1,
        "valid_from": "",
        "provenance": {
            "source": "",
            "recorded_by": "",
            "note": "",
            "license_note": "",
        },
        "groups": [
            {
                "sku_cluster": group["sku_cluster"],
                "items": [],
                "retire": [],
            }
            for group in TARGET_GROUPS
        ],
    }


def _normalize(document: dict, *, allow_example: bool) -> dict:
    if not isinstance(document, dict):
        raise AmazonBsrError("bad_mapping", "mapping file must be a JSON object")
    if document.get("_template") is True:
        raise AmazonBsrError(
            "template_not_importable",
            "this file is still a template; fill it and remove _template before import",
        )
    if document.get("_example") is True and not allow_example:
        raise AmazonBsrError("example_refused", "files marked _example are test fixtures and are not imported")
    version = check_version(document.get("mapping_version"))
    if document.get("domain_id") != 1:
        raise AmazonBsrError("domain_not_enabled", "mapping domain_id must be 1 (Amazon.com)")
    valid_from = parse_date(document.get("valid_from"))
    provenance = check_provenance(document.get("provenance"))
    groups = document.get("groups")
    if not isinstance(groups, list) or not groups:
        raise AmazonBsrError("groups_required", "groups must include each sku cluster being updated")
    seen: set[str] = set()
    normalized = []
    for group in groups:
        if not isinstance(group, dict):
            raise AmazonBsrError("bad_mapping", "each group must be an object")
        sku = group.get("sku_cluster")
        if sku not in GROUP_BY_SKU:
            raise AmazonBsrError("unknown_sku_cluster", f"{sku} is outside the four initial groups")
        items = []
        for raw in group.get("items") or []:
            if not isinstance(raw, dict):
                raise AmazonBsrError("bad_mapping", "each item must be an object")
            asin = check_asin(raw.get("asin"), allow_example=allow_example)
            if asin in seen:
                raise AmazonBsrError("duplicate_asin", f"{asin} appears twice in one mapping file")
            seen.add(asin)
            role = raw.get("role")
            parent = validate_variation(role, asin, raw.get("parent_asin"), raw.get("variation_attributes"))
            attributes = raw.get("product_attributes") or {}
            facet = validate_attributes(sku, attributes, raw)
            item = {
                "asin": asin,
                "role": role,
                "parent_asin": parent,
                "variation_attributes": raw.get("variation_attributes") or [],
                "product_attributes": attributes,
                "category_ids": validate_category_ids(raw.get("category_ids")),
                "inclusion_reason": _reason(raw.get("inclusion_reason"), "inclusion_reason"),
                "inclusion_facet": facet,
                "multi_facet_reason": raw.get("multi_facet_reason"),
                "multi_style_reason": raw.get("multi_style_reason"),
            }
            item["content_hash"] = canonical_hash(item)
            items.append(item)
        retires = []
        for raw in group.get("retire") or []:
            if not isinstance(raw, dict):
                raise AmazonBsrError("bad_mapping", "retire entries must be objects")
            asin = check_asin(raw.get("asin"), allow_example=allow_example)
            if asin in seen:
                raise AmazonBsrError("duplicate_asin", f"{asin} is both added and retired")
            seen.add(asin)
            retires.append({"asin": asin, "reason": _reason(raw.get("reason"), "retire.reason")})
        normalized.append({"sku_cluster": sku, "items": items, "retire": retires})
    body = {
        "domain_id": 1,
        "valid_from": valid_from,
        "provenance": provenance,
        "groups": normalized,
    }
    return {
        "mapping_version": version,
        "valid_from": valid_from,
        "provenance": provenance,
        "groups": normalized,
        "content_hash": canonical_hash(body),
        "item_count": sum(len(group["items"]) for group in normalized),
    }


def import_mapping(con, document: dict, *, allow_example: bool = False, dry_run: bool = False, now: str | None = None) -> dict:
    require_migrated(con)
    if allow_example:
        _refuse_example_on_signal_db(con)
    normalized = _normalize(document, allow_example=allow_example)
    recorded_at = now or now_utc()
    existing = con.execute(
        "SELECT content_hash FROM amazon_mapping_version WHERE mapping_version = ?",
        (normalized["mapping_version"],),
    ).fetchone()
    if existing is not None:
        if existing["content_hash"] != normalized["content_hash"]:
            raise AmazonBsrError(
                "mapping_version_immutable",
                "that mapping_version already exists with different contents; choose a new version",
            )
        return {
            "ok": True,
            "status": "duplicate",
            "mapping_version": normalized["mapping_version"],
            "item_count": normalized["item_count"],
            "dry_run": dry_run,
            "wrote": False,
        }
    planned = {"insert": normalized["item_count"], "retire": sum(len(g["retire"]) for g in normalized["groups"])}
    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "mapping_version": normalized["mapping_version"],
            "planned": planned,
            "wrote": False,
        }
    with transaction(con):
        return _write_mapping(con, normalized, recorded_at)


def _write_mapping(con, normalized: dict, recorded_at: str) -> dict:
    for group in normalized["groups"]:
        for item in group["items"]:
            current = con.execute(
                """
                SELECT sku_cluster FROM amazon_asin_map
                WHERE asin = ? AND domain_id = 1 AND is_current = 1
                """,
                (item["asin"],),
            ).fetchone()
            if current is not None and current["sku_cluster"] != group["sku_cluster"]:
                raise AmazonBsrError(
                    "asin_in_other_group",
                    f"{item['asin']} is current in {current['sku_cluster']}; retire it there before mapping it here",
                )
    provenance_json = json.dumps(normalized["provenance"], ensure_ascii=False, sort_keys=True)
    con.execute(
        """
        INSERT INTO amazon_mapping_version(
          mapping_version, domain_id, valid_from, provenance_json, content_hash, recorded_at, item_count
        ) VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (
            normalized["mapping_version"],
            normalized["valid_from"],
            provenance_json,
            normalized["content_hash"],
            recorded_at,
            normalized["item_count"],
        ),
    )
    for group in normalized["groups"]:
        for item in group["items"]:
            previous = con.execute(
                """
                SELECT map_id FROM amazon_asin_map
                WHERE sku_cluster = ? AND asin = ? AND domain_id = 1 AND is_current = 1
                """,
                (group["sku_cluster"], item["asin"]),
            ).fetchone()
            if previous is not None:
                con.execute(
                    "UPDATE amazon_asin_map SET valid_to = ?, is_current = 0 WHERE map_id = ?",
                    (normalized["valid_from"], previous["map_id"]),
                )
            con.execute(
                """
                INSERT INTO amazon_asin_map(
                  mapping_version, sku_cluster, asin, domain_id, role, parent_asin,
                  variation_attributes_json, product_attributes_json, category_ids_json,
                  inclusion_reason, inclusion_facet, provenance_json, valid_from, valid_to,
                  is_current, recorded_at, content_hash
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?, ?)
                """,
                (
                    normalized["mapping_version"],
                    group["sku_cluster"],
                    item["asin"],
                    item["role"],
                    item["parent_asin"],
                    json.dumps(item["variation_attributes"], ensure_ascii=False, sort_keys=True),
                    json.dumps(item["product_attributes"], ensure_ascii=False, sort_keys=True),
                    json.dumps(item["category_ids"], ensure_ascii=False),
                    item["inclusion_reason"],
                    item["inclusion_facet"],
                    provenance_json,
                    normalized["valid_from"],
                    recorded_at,
                    item["content_hash"],
                ),
            )
        for retired in group["retire"]:
            current = con.execute(
                """
                SELECT map_id FROM amazon_asin_map
                WHERE sku_cluster = ? AND asin = ? AND domain_id = 1 AND is_current = 1
                """,
                (group["sku_cluster"], retired["asin"]),
            ).fetchone()
            if current is None:
                raise AmazonBsrError("retire_missing", f"{retired['asin']} is not a current mapping in {group['sku_cluster']}")
            con.execute(
                "UPDATE amazon_asin_map SET valid_to = ?, is_current = 0 WHERE map_id = ?",
                (normalized["valid_from"], current["map_id"]),
            )
    pools = refresh_pool_counts(con, recorded_at)
    return {
        "ok": True,
        "status": "imported",
        "mapping_version": normalized["mapping_version"],
        "item_count": normalized["item_count"],
        "pools": pools,
        "wrote": True,
        "dry_run": False,
    }


def load_mapping_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise AmazonBsrError("bad_mapping", f"mapping file is not JSON: {exc}") from exc


def _refuse_example_on_signal_db(con) -> None:
    for row in con.execute("PRAGMA database_list"):
        text = str(row["file"] or "")
        if text.endswith("dacu_signals.sqlite") or "/dacu-signal/" in text:
            raise AmazonBsrError(
                "example_refused",
                "example mappings cannot be written to the signal database",
            )
