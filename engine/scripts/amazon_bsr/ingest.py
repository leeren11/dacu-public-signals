"""Append Keepa product JSON into raw payloads and observations.

Re-importing the same canonical payload does not duplicate observations.
A different value at the same observed_at is inserted as a new revision.
first_available_to_system is when this database received the point, which is
later than observed_at for historical backfill.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from amazon_bsr.db import LICENSE_NOTE, SOURCE_ID, pack_payload, require_migrated, transaction
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.keepa_decode import decode_product
from amazon_bsr.policies import EXAMPLE_PREFIX, is_example_asin
from amazon_bsr.redact import canonical_bytes, canonical_hash, redact_obj, sha256_hex, text_secret_count
from amazon_bsr.timeutil import format_utc, now_utc, parse_utc

OBSERVATION_COLUMNS = (
    "raw_id",
    "batch_id",
    "asin",
    "domain_id",
    "series_kind",
    "category_id",
    "category_name",
    "category_resolution",
    "observed_at",
    "keepa_time_minutes",
    "retrieved_at",
    "first_available_to_system",
    "value_num",
    "value_text",
    "value_missing_reason",
    "sentinel_raw",
    "currency",
    "price_type",
    "price_cents",
    "shipping_cents",
    "price_basis",
    "count_kind",
    "count_scope",
    "definition_variant",
    "source_field",
    "source_updated_at",
    "source_update_status",
    "source_update_reason",
    "stock_qty",
    "offer_id",
    "seller_id",
    "offer_condition",
    "is_valid_measurement",
    "revision_seq",
    "supersedes_observation_id",
    "revision_reason",
    "natural_key",
    "conflict_key",
)


def parse_response_timestamp(value: object) -> str | None:
    """Keepa response `timestamp` is Unix epoch milliseconds in the product-request examples.

    Values that are too small to be Unix seconds are not treated as Keepa minutes.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value > 10**12:
        return format_utc(datetime.fromtimestamp(value / 1000, timezone.utc))
    if value > 10**9:
        return format_utc(datetime.fromtimestamp(value, timezone.utc))
    return None


def split_document(parsed: object) -> tuple[dict | None, list[dict]]:
    if isinstance(parsed, dict) and isinstance(parsed.get("products"), list):
        products = [item for item in parsed["products"] if isinstance(item, dict)]
        envelope = {key: value for key, value in parsed.items() if key != "products"}
        envelope["product_asins"] = [item.get("asin") for item in products]
        return envelope, products
    if isinstance(parsed, dict) and "asin" in parsed:
        return None, [parsed]
    if isinstance(parsed, list):
        products = []
        envelope = None
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("products"), list):
                extra_env, extra_products = split_document(item)
                products.extend(extra_products)
                envelope = extra_env
            elif isinstance(item, dict):
                products.append(item)
        return envelope, products
    raise AmazonBsrError("bad_keepa_json", "expected a Keepa response, a product object, a list, or JSONL")


def loads_keepa_bytes(raw: bytes) -> tuple[object, list[dict], dict | None]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise AmazonBsrError("bad_keepa_json", "Keepa input must be UTF-8 JSON") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed_lines = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed_lines.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AmazonBsrError("bad_keepa_json", f"JSONL line {line_number} is not JSON") from exc
        if not parsed_lines:
            raise AmazonBsrError("bad_keepa_json", "file is empty")
        envelope, products = split_document(parsed_lines)
        return parsed_lines, products, envelope
    envelope, products = split_document(parsed)
    return parsed, products, envelope


def _example_guard(parsed: object, products: list[dict], *, allow_example: bool) -> None:
    marked = isinstance(parsed, dict) and parsed.get("_example") is True
    if isinstance(parsed, list) and any(isinstance(item, dict) and item.get("_example") is True for item in parsed):
        marked = True
    if marked and not allow_example:
        raise AmazonBsrError("example_refused", "files marked _example are test fixtures and are not imported")
    if allow_example:
        return
    for product in products:
        asin = product.get("asin")
        if isinstance(asin, str) and is_example_asin(asin):
            raise AmazonBsrError(
                "example_asin_refused",
                f"{asin} starts with {EXAMPLE_PREFIX}, which is reserved for tests",
            )


def _refuse_example_db(con) -> None:
    for row in con.execute("PRAGMA database_list"):
        text = str(row["file"] or "")
        if text.endswith("dacu_signals.sqlite") or "/dacu-signal/" in text:
            raise AmazonBsrError("example_refused", "example payloads cannot be written to the signal database")


def begin_batch(
    con,
    *,
    source_kind: str,
    started_at: str,
    request_params: dict,
    license_note: str,
    file_name: str | None,
    file_sha256: str | None,
    known_since: str | None,
    known_since_reason: str | None,
    retrieved_at: str | None,
    source_response_at: str | None,
    token_budget: int | None,
    tokens_consumed: int | None,
    tokens_left: int | None,
    refill_in: int | None,
    refill_rate: int | None,
    secrets_redacted: int,
) -> str:
    batch_id = "batch_" + canonical_hash(
        {
            "started_at": started_at,
            "file_sha256": file_sha256,
            "source_kind": source_kind,
            "request": request_params,
            "nonce": canonical_hash(request_params)[:12],
        }
    )[:24]
    # The hash above can collide for two identical requests at the same second.
    # Include a random suffix only when the id is taken.
    existing = con.execute("SELECT 1 FROM amazon_ingest_batch WHERE batch_id = ?", (batch_id,)).fetchone()
    if existing is not None:
        from uuid import uuid4

        batch_id = "batch_" + uuid4().hex[:24]
    con.execute(
        """
        INSERT INTO amazon_ingest_batch(
          batch_id, source_id, source_kind, domain_id, started_at, finished_at, status,
          status_reason, request_params_json, sanitized, token_budget, tokens_consumed_reported,
          tokens_left_reported, refill_in_reported, refill_rate_reported, known_since,
          known_since_reason, retrieved_at, source_response_at, license_note, file_name,
          file_sha256, secrets_redacted
        ) VALUES (
          ?, ?, ?, 1, ?, NULL, 'open', NULL, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            batch_id,
            SOURCE_ID,
            source_kind,
            started_at,
            json.dumps(request_params, ensure_ascii=False, sort_keys=True),
            token_budget,
            tokens_consumed,
            tokens_left,
            refill_in,
            refill_rate,
            known_since,
            known_since_reason,
            retrieved_at,
            source_response_at,
            license_note,
            file_name,
            file_sha256,
            secrets_redacted,
        ),
    )
    return batch_id


def finish_batch(con, batch_id: str, *, status: str, status_reason: str, finished_at: str, counts: dict) -> None:
    con.execute(
        """
        UPDATE amazon_ingest_batch
        SET status = ?, status_reason = ?, finished_at = ?,
            item_count = ?, inserted_observations = ?, duplicate_observations = ?,
            revision_observations = ?
        WHERE batch_id = ?
        """,
        (
            status,
            status_reason,
            finished_at,
            counts.get("products", 0),
            counts.get("inserted", 0),
            counts.get("duplicate", 0),
            counts.get("revision", 0),
            batch_id,
        ),
    )


def _store_blob(con, *, batch_id: str, role: str, logical: bytes, content_hash: str, asin: str | None, retrieved_at: str, first_available: str, license_note: str, secrets: int) -> tuple[str, bool]:
    raw_id = f"raw_{role[:1]}_{content_hash[:24]}"
    existing = con.execute(
        "SELECT raw_id FROM amazon_raw_payload WHERE payload_role = ? AND content_hash = ?",
        (role, content_hash),
    ).fetchone()
    if existing is not None:
        return existing["raw_id"], False
    encoding, blob = pack_payload(logical)
    con.execute(
        """
        INSERT INTO amazon_raw_payload(
          raw_id, batch_id, payload_role, asin, domain_id, content_hash, payload_encoding,
          payload_blob, blob_sha256, uncompressed_bytes, secrets_redacted, retrieved_at,
          first_available_to_system, license_note
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_id,
            batch_id,
            role,
            asin,
            content_hash,
            encoding,
            blob,
            sha256_hex(blob),
            len(logical),
            secrets,
            retrieved_at,
            first_available,
            license_note,
        ),
    )
    return raw_id, True


def _insert_observation(con, row: dict) -> str:
    existing = con.execute(
        "SELECT observation_id FROM amazon_observation WHERE natural_key = ?",
        (row["natural_key"],),
    ).fetchone()
    if existing is not None:
        return "duplicate"
    previous = con.execute(
        """
        SELECT observation_id, revision_seq FROM amazon_observation
        WHERE conflict_key = ?
        ORDER BY revision_seq DESC
        LIMIT 1
        """,
        (row["conflict_key"],),
    ).fetchone()
    if previous is None:
        revision = 1
        supersedes = None
        reason = None
        kind = "inserted"
    else:
        revision = previous["revision_seq"] + 1
        supersedes = previous["observation_id"]
        reason = "value_changed_at_same_observed_at"
        kind = "revision"
    values = dict(row)
    values["revision_seq"] = revision
    values["supersedes_observation_id"] = supersedes
    values["revision_reason"] = reason
    columns = ", ".join(OBSERVATION_COLUMNS)
    marks = ", ".join("?" for _ in OBSERVATION_COLUMNS)
    con.execute(
        f"INSERT INTO amazon_observation({columns}) VALUES ({marks})",
        tuple(values.get(column) for column in OBSERVATION_COLUMNS),
    )
    return kind


def _store_product(con, product: dict, *, batch_id: str, raw_id: str, retrieved_at: str, first_available: str) -> dict:
    decoded = decode_product(product, domain_id=1)
    counts = {"inserted": 0, "duplicate": 0, "revision": 0, "rejected": 0}
    if decoded.rejected_reason:
        counts["rejected"] = 1
        counts["reject_reason"] = decoded.rejected_reason
        return counts
    snapshot = decoded.snapshot or {}
    con.execute(
        """
        INSERT INTO amazon_product_snapshot(
          raw_id, asin, domain_id, product_type, title, brand, color, size, material,
          parent_asin, root_category_id, category_ids_json, attributes_json, decode_notes_json,
          listed_since_raw, listed_since_at, tracking_since_at, last_update_at,
          last_rating_update_at, last_stock_update_at, availability_amazon, observed_at,
          retrieved_at, first_available_to_system
        ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_id,
            snapshot.get("asin"),
            snapshot.get("product_type"),
            snapshot.get("title"),
            snapshot.get("brand"),
            snapshot.get("color"),
            snapshot.get("size"),
            snapshot.get("material"),
            snapshot.get("parent_asin"),
            snapshot.get("root_category_id"),
            json.dumps(snapshot.get("category_ids_json") or [], ensure_ascii=False),
            json.dumps(snapshot.get("attributes_json") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(snapshot.get("decode_notes_json") or [], ensure_ascii=False),
            snapshot.get("listed_since_raw"),
            snapshot.get("listed_since_at"),
            snapshot.get("tracking_since_at"),
            snapshot.get("last_update_at"),
            snapshot.get("last_rating_update_at"),
            snapshot.get("last_stock_update_at"),
            snapshot.get("availability_amazon"),
            snapshot.get("observed_at"),
            retrieved_at,
            first_available,
        ),
    )
    for name in decoded.category_names:
        con.execute(
            """
            INSERT OR IGNORE INTO amazon_category_name(domain_id, category_id, name, raw_id, recorded_at)
            VALUES (1, ?, ?, ?, ?)
            """,
            (name["category_id"], name["name"], raw_id, first_available),
        )
    for item in decoded.variations:
        con.execute(
            """
            INSERT INTO amazon_variation_seen(
              raw_id, domain_id, parent_asin, child_asin, attributes_json, image_filename,
              variation_scope, observed_at, retrieved_at, first_available_to_system, natural_key
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_id,
                item["parent_asin"],
                item["child_asin"],
                json.dumps(item["attributes_json"], ensure_ascii=False, sort_keys=True),
                item["image_filename"],
                item["variation_scope"],
                snapshot.get("observed_at"),
                retrieved_at,
                first_available,
                canonical_hash({"raw_id": raw_id, "identity": item["natural_identity"]}),
            ),
        )
    seen_fields = set()
    for presence in decoded.presence:
        if presence["source_field"] in seen_fields:
            continue
        seen_fields.add(presence["source_field"])
        con.execute(
            """
            INSERT INTO amazon_series_presence(raw_id, source_field, present, point_count, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (raw_id, presence["source_field"], presence["present"], presence["point_count"], presence["note"]),
        )
    seen_keys = set()
    for point in decoded.points:
        if point["natural_key"] in seen_keys:
            counts["duplicate"] += 1
            continue
        seen_keys.add(point["natural_key"])
        point = dict(point)
        point.update(
            {
                "raw_id": raw_id,
                "batch_id": batch_id,
                "retrieved_at": retrieved_at,
                "first_available_to_system": first_available,
            }
        )
        kind = _insert_observation(con, point)
        counts[kind] += 1
    return counts


def import_parsed(
    con,
    raw: bytes,
    parsed: object,
    products: list[dict],
    envelope: dict | None,
    *,
    source_kind: str,
    domain_id: int = 1,
    retrieved_at: str | None = None,
    known_since: str | None = None,
    known_since_reason: str | None = None,
    license_note: str | None = None,
    file_name: str | None = None,
    request_params: dict | None = None,
    token_budget: int | None = None,
    allow_example: bool = False,
    dry_run: bool = False,
    now: str | None = None,
) -> dict:
    require_migrated(con)
    if domain_id != 1:
        raise AmazonBsrError("domain_not_enabled", "import domain must be 1")
    if allow_example:
        _refuse_example_db(con)
    _example_guard(parsed, products, allow_example=allow_example)
    if not products:
        raise AmazonBsrError("no_products", "no Keepa product objects were found")
    clock = now or now_utc()
    parse_utc(clock)
    if known_since is not None:
        parse_utc(known_since)
        if known_since > clock:
            raise AmazonBsrError("bad_timestamp", "known-since cannot be in the future")
        if not isinstance(known_since_reason, str) or len(known_since_reason.strip()) < 12:
            raise AmazonBsrError(
                "known_since_reason_required",
                "known-since rewrites when this system knew the history; explain it in at least 12 characters",
            )
    response_at = parse_response_timestamp((envelope or {}).get("timestamp")) if envelope else None
    if retrieved_at is None:
        retrieved_at = response_at or clock
    parse_utc(retrieved_at)
    if retrieved_at > clock:
        raise AmazonBsrError("bad_timestamp", "retrieved-at cannot be after the ingest clock")
    first_available = known_since or clock
    counter = [0]
    if text_secret_count(raw.decode("utf-8-sig", errors="replace")):
        counter[0] += 1
    redacted_doc = redact_obj(parsed, counter)
    redacted_products = []
    for product in products:
        redacted_products.append(redact_obj(product, counter))
    logical_file = canonical_bytes(redacted_doc)
    file_hash = sha256_hex(logical_file)
    original_sha = sha256_hex(raw)
    params = request_params
    if params is None:
        embedded = None
        if isinstance(parsed, dict):
            embedded = parsed.get("request") or parsed.get("requestParameters")
        if embedded is not None:
            params = redact_obj(embedded, counter)
        else:
            params = {"request_parameters": "not_provided_offline_file", "domain": 1}
    if not isinstance(params, dict):
        params = {"request_parameters": "unusable", "domain": 1}
    params = redact_obj(params, counter)
    license_text = license_note.strip() if isinstance(license_note, str) and license_note.strip() else LICENSE_NOTE
    tokens = _int_field(envelope, "tokensConsumed")
    tokens_left = _int_field(envelope, "tokensLeft")
    refill_in = _int_field(envelope, "refillIn")
    refill_rate = _int_field(envelope, "refillRate")
    decoded_products = [decode_product(product, domain_id=1) for product in redacted_products]
    rejected = [item.rejected_reason for item in decoded_products if item.rejected_reason]
    accepted = [item for item in decoded_products if not item.rejected_reason]
    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "wrote": False,
            "products": len(products),
            "accepted": len(accepted),
            "rejected": rejected,
            "secrets_redacted": counter[0],
            "points": sum(len(item.points) for item in accepted),
            "file_sha256": original_sha,
        }
    if not accepted:
        raise AmazonBsrError("rejected_products", ", ".join(sorted(set(rejected))) or "no usable products")
    with transaction(con):
        return _write_import(
            con,
            redacted_products=redacted_products,
            decoded_products=decoded_products,
            logical_file=logical_file,
            file_hash=file_hash,
            original_sha=original_sha,
            envelope=None if envelope is None else redact_obj(envelope, counter),
            params=params if isinstance(params, dict) else {"request_parameters": "redacted"},
            license_text=license_text,
            file_name=file_name,
            known_since=known_since,
            known_since_reason=known_since_reason.strip() if isinstance(known_since_reason, str) else None,
            retrieved_at=retrieved_at,
            response_at=response_at,
            token_budget=token_budget,
            tokens=tokens,
            tokens_left=tokens_left,
            refill_in=refill_in,
            refill_rate=refill_rate,
            secrets=counter[0],
            source_kind=source_kind,
            clock=clock,
            first_available=first_available,
            rejected=rejected,
        )


def _write_import(con, **kw) -> dict:
    redacted_products = kw["redacted_products"]
    decoded_products = kw["decoded_products"]
    secrets = kw["secrets"]
    rejected = kw["rejected"]
    batch_id = begin_batch(
        con,
        source_kind=kw["source_kind"],
        started_at=kw["clock"],
        request_params=kw["params"],
        license_note=kw["license_text"],
        file_name=kw["file_name"],
        file_sha256=kw["original_sha"],
        known_since=kw["known_since"],
        known_since_reason=kw["known_since_reason"],
        retrieved_at=kw["retrieved_at"],
        source_response_at=kw["response_at"],
        token_budget=kw["token_budget"],
        tokens_consumed=kw["tokens"],
        tokens_left=kw["tokens_left"],
        refill_in=kw["refill_in"],
        refill_rate=kw["refill_rate"],
        secrets_redacted=secrets,
    )
    _store_blob(
        con,
        batch_id=batch_id,
        role="file",
        logical=kw["logical_file"],
        content_hash=kw["file_hash"],
        asin=None,
        retrieved_at=kw["retrieved_at"],
        first_available=kw["first_available"],
        license_note=kw["license_text"],
        secrets=secrets,
    )
    if kw["envelope"] is not None:
        envelope_logical = canonical_bytes(kw["envelope"])
        _store_blob(
            con,
            batch_id=batch_id,
            role="response_envelope",
            logical=envelope_logical,
            content_hash=sha256_hex(envelope_logical),
            asin=None,
            retrieved_at=kw["retrieved_at"],
            first_available=kw["first_available"],
            license_note=kw["license_text"],
            secrets=secrets,
        )
    totals = {"inserted": 0, "duplicate": 0, "revision": 0, "products": 0}
    for product, decoded in zip(redacted_products, decoded_products):
        if decoded.rejected_reason:
            continue
        logical = canonical_bytes(product)
        content_hash = sha256_hex(logical)
        raw_id, created = _store_blob(
            con,
            batch_id=batch_id,
            role="product",
            logical=logical,
            content_hash=content_hash,
            asin=decoded.asin,
            retrieved_at=kw["retrieved_at"],
            first_available=kw["first_available"],
            license_note=kw["license_text"],
            secrets=secrets,
        )
        totals["products"] += 1
        if not created:
            totals["duplicate"] += len(decoded.points)
            continue
        counts = _store_product(
            con,
            product,
            batch_id=batch_id,
            raw_id=raw_id,
            retrieved_at=kw["retrieved_at"],
            first_available=kw["first_available"],
        )
        totals["inserted"] += counts["inserted"]
        totals["duplicate"] += counts["duplicate"]
        totals["revision"] += counts["revision"]
    if totals["inserted"] == 0 and totals["revision"] == 0:
        status = "duplicate"
        reason = "canonical payload already stored"
    elif rejected:
        status = "partial"
        reason = "some products were rejected; " + ",".join(sorted(set(rejected)))
    else:
        status = "imported"
        reason = "offline Keepa JSON stored" if kw["source_kind"] == "offline_file" else "Keepa response stored"
    finish_batch(
        con,
        batch_id,
        status=status,
        status_reason=reason,
        finished_at=kw["clock"],
        counts=totals,
    )
    return {
        "ok": True,
        "status": status,
        "status_reason": reason,
        "batch_id": batch_id,
        "wrote": True,
        "products": totals["products"],
        "inserted_observations": totals["inserted"],
        "duplicate_observations": totals["duplicate"],
        "revision_observations": totals["revision"],
        "rejected": rejected,
        "secrets_redacted": secrets,
        "first_available_to_system": kw["first_available"],
        "retrieved_at": kw["retrieved_at"],
        "file_sha256": kw["original_sha"],
    }


def import_keepa_bytes(con, raw: bytes, **kwargs) -> dict:
    parsed, products, envelope = loads_keepa_bytes(raw)
    return import_parsed(con, raw, parsed, products, envelope, **kwargs)


def import_keepa_file(con, path: Path | str, **kwargs) -> dict:
    path = Path(path)
    if not path.is_file():
        raise AmazonBsrError("local_file_missing", f"{path} is not a file")
    raw = path.read_bytes()
    kwargs.setdefault("file_name", path.name)
    kwargs.setdefault("source_kind", "offline_file")
    return import_keepa_bytes(con, raw, **kwargs)


def _int_field(envelope: dict | None, name: str) -> int | None:
    if not envelope or name not in envelope:
        return None
    value = envelope.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
