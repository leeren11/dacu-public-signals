"""Optional Keepa product fetch.

Nothing in this module runs unless live_confirmed is true and KEEPA_API_KEY is set.
The published token schedule is not used as a prediction of tokensConsumed.
A basic request uses the documented minimum of 1 token per product only as a
lower bound that can stop the next call. The number that is stored is the
tokensConsumed field from the response. If that field is missing, the run stops
instead of inventing a cost.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from amazon_bsr.db import connect_rw, require_migrated, transaction
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.ingest import begin_batch, finish_batch, import_keepa_bytes
from amazon_bsr.policies import check_asin
from amazon_bsr.redact import redact_text
from amazon_bsr.timeutil import now_utc

ENDPOINT = "https://api.keepa.com/product"
DOCS = "https://keepa.com/api-docs/product.html"
# Documented basic product-request cost. Not an estimate of a future response.
PUBLISHED_BASIC_MINIMUM_PER_PRODUCT = 1


def default_fetch(url: str, timeout: int = 60) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "dacu-amazon-bsr/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _asins_from_file(path: str) -> list[str]:
    if "://" in path or path.lower().startswith("http"):
        raise AmazonBsrError("live_forbidden", "ASIN input must be a local file")
    found = []
    for line in open(path, encoding="utf-8"):
        text = line.strip()
        if text and not text.startswith("#"):
            found.append(text)
    return found


def _dedupe(asins: list[str]) -> list[str]:
    seen = set()
    out = []
    for asin in asins:
        if asin not in seen:
            seen.add(asin)
            out.append(asin)
    return out


def live_fetch(
    db_path,
    *,
    live_confirmed: bool,
    asins: list[str],
    asin_file: str | None,
    domain_id: int,
    token_budget: int,
    batch_size: int,
    days: int | None = None,
    stats_days: int | None = None,
    rating: bool = False,
    offers: int | None = None,
    stock: bool = False,
    buybox: bool = False,
    update_hours: int | None = None,
    fetch=None,
    key: str | None = None,
    now: str | None = None,
) -> dict:
    if fetch is None:
        fetch = default_fetch
    if not live_confirmed:
        raise AmazonBsrError("live_not_confirmed", "refusing the Keepa API without --live-fetch")
    secret = os.environ.get("KEEPA_API_KEY", "") if key is None else key
    if not isinstance(secret, str) or not secret.strip():
        return {
            "ok": True,
            "status": "unavailable",
            "live_api": "unavailable_no_key",
            "fetched": False,
            "requests": 0,
            "summary_zh": "未设置 KEEPA_API_KEY。实时采集不可用，这不是流水线失败，也没有发出请求。",
        }
    if domain_id != 1:
        raise AmazonBsrError("domain_not_enabled", "live fetch domain must be 1")
    if not isinstance(token_budget, int) or isinstance(token_budget, bool) or token_budget < 1:
        raise AmazonBsrError("token_budget", "pass an explicit positive --token-budget; this tool does not estimate a cost")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 100:
        raise AmazonBsrError("batch_size", "--batch-size must be an integer from 1 to 100")
    extra = {
        "rating": rating,
        "offers": offers,
        "stock": stock,
        "buybox": buybox,
        "update": update_hours,
    }
    uses_extra = bool(rating or stock or buybox or offers or update_hours is not None)
    if uses_extra and batch_size != 1:
        raise AmazonBsrError(
            "refusing_to_guess_token_cost",
            "rating, offers, stock, buybox, and update have conditional token costs; use --batch-size 1",
        )
    if offers is not None and (not isinstance(offers, int) or isinstance(offers, bool) or not 20 <= offers <= 100):
        raise AmazonBsrError("offers", "Keepa documents offers as an integer from 20 to 100")
    chosen = list(asins)
    if asin_file:
        chosen.extend(_asins_from_file(asin_file))
    chosen = _dedupe([check_asin(asin, allow_example=False) for asin in chosen])
    if not chosen:
        raise AmazonBsrError("asin_required", "pass at least one ASIN")
    con = connect_rw(db_path, create=False)
    try:
        require_migrated(con)
    finally:
        con.close()
    clock = now or now_utc()
    consumed = 0
    calls = []
    stopped = None
    for start in range(0, len(chosen), batch_size):
        chunk = chosen[start : start + batch_size]
        remaining = token_budget - consumed
        if remaining < 1:
            stopped = "budget_reached"
            break
        if not uses_extra and len(chunk) > remaining:
            # Published minimum is 1 token per product for a basic request.
            # This only prevents the next call; it is not the cost Keepa will report.
            chunk = chunk[:remaining]
            if not chunk:
                stopped = "published_minimum_lower_bound"
                break
        public_params = {
            "domain": 1,
            "asin": chunk,
            "history": 1,
        }
        if days is not None:
            public_params["days"] = days
        if stats_days is not None:
            public_params["stats"] = stats_days
        if rating:
            public_params["rating"] = 1
        if offers is not None:
            public_params["offers"] = offers
        if stock:
            public_params["stock"] = 1
        if buybox:
            public_params["buybox"] = 1
        if update_hours is not None:
            public_params["update"] = update_hours
        query = {key_name: value for key_name, value in public_params.items() if key_name != "asin"}
        query["asin"] = ",".join(chunk)
        query["key"] = secret
        url = ENDPOINT + "?" + urllib.parse.urlencode(query)
        sanitized = dict(public_params)
        sanitized["key"] = "[REDACTED]"
        try:
            status, body = fetch(url)
            error_text = None
        except Exception as exc:
            status, body = 0, b""
            error_text = redact_text(str(exc), [secret])[:500]
        payload = None
        if body:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                error_text = error_text or "response was not JSON"
                payload = None
        reported = payload.get("tokensConsumed") if isinstance(payload, dict) else None
        if isinstance(reported, bool) or not isinstance(reported, int):
            reported = None
        call = {
            "http_status": status,
            "tokens_consumed": reported,
            "asins": chunk,
            "error": error_text,
        }
        if reported is None:
            _record_call(
                db_path,
                sanitized=sanitized,
                status=status,
                payload=payload,
                error_text=error_text or "tokensConsumed missing; refusing to invent a token cost",
                token_budget=token_budget,
                now=clock,
                secret=secret,
            )
            call["stored"] = False
            calls.append(call)
            stopped = "tokens_unreported"
            break
        consumed += reported
        if status != 200 or not isinstance(payload, dict) or payload.get("error") or "products" not in payload:
            message = error_text or _error_message(payload, secret)
            _record_call(
                db_path,
                sanitized=sanitized,
                status=status,
                payload=payload,
                error_text=message,
                token_budget=token_budget,
                now=clock,
                secret=secret,
            )
            call["stored"] = False
            calls.append(call)
            stopped = "request_failed"
            break
        con = connect_rw(db_path, create=False)
        try:
            stored = import_keepa_bytes(
                con,
                body,
                source_kind="live_api",
                domain_id=1,
                request_params=sanitized,
                token_budget=token_budget,
                allow_example=False,
                now=clock,
            )
        finally:
            con.close()
        _attach_request(db_path, stored.get("batch_id"), sanitized, status, payload, None, clock)
        call["stored"] = True
        call["batch_id"] = stored.get("batch_id")
        calls.append(call)
        if consumed >= token_budget:
            stopped = "budget_reached"
            break
    return {
        "ok": True,
        "status": "completed" if stopped is None else stopped,
        "fetched": True,
        "live_api": "called",
        "requests": len(calls),
        "tokens_consumed_reported": consumed,
        "token_budget": token_budget,
        "token_note": (
            "tokens_consumed_reported is the sum of Keepa tokensConsumed fields. "
            f"The published basic minimum is {PUBLISHED_BASIC_MINIMUM_PER_PRODUCT} per product "
            f"({DOCS}) and was not used as an estimate."
        ),
        "published_schedule_url": DOCS,
        "estimated_tokens": None,
        "calls": calls,
        "stopped": stopped,
    }


def _error_message(payload: object, secret: str) -> str:
    if isinstance(payload, dict) and payload.get("error") is not None:
        return redact_text(json.dumps(payload.get("error"), ensure_ascii=False), [secret])[:500]
    return "Keepa response did not include products"


def _record_call(db_path, *, sanitized, status, payload, error_text, token_budget, now, secret) -> None:
    con = connect_rw(db_path, create=False)
    try:
        with transaction(con):
            batch_id = begin_batch(
                con,
                source_kind="live_api",
                started_at=now,
                request_params=sanitized,
                license_note="Subject to the operator's own Keepa license. Raw public export is off by default.",
                file_name=None,
                file_sha256=None,
                known_since=None,
                known_since_reason=None,
                retrieved_at=now,
                source_response_at=None,
                token_budget=token_budget,
                tokens_consumed=payload.get("tokensConsumed") if isinstance(payload, dict) and isinstance(payload.get("tokensConsumed"), int) else None,
                tokens_left=payload.get("tokensLeft") if isinstance(payload, dict) and isinstance(payload.get("tokensLeft"), int) else None,
                refill_in=payload.get("refillIn") if isinstance(payload, dict) and isinstance(payload.get("refillIn"), int) else None,
                refill_rate=payload.get("refillRate") if isinstance(payload, dict) and isinstance(payload.get("refillRate"), int) else None,
                secrets_redacted=0,
            )
            _insert_request(con, batch_id, sanitized, status, payload, redact_text(error_text or "", [secret]), now)
            finish_batch(
                con,
                batch_id,
                status="failed",
                status_reason=redact_text(error_text or "request failed", [secret])[:300],
                finished_at=now,
                counts={"products": 0, "inserted": 0, "duplicate": 0, "revision": 0},
            )
    finally:
        con.close()


def _attach_request(db_path, batch_id: str | None, sanitized, status, payload, error_text, now: str) -> None:
    if not batch_id:
        return
    con = connect_rw(db_path, create=False)
    try:
        with transaction(con):
            _insert_request(con, batch_id, sanitized, status, payload, error_text, now)
    finally:
        con.close()


def _insert_request(con, batch_id: str, sanitized: dict, status: int | None, payload: object, error_text: str | None, now: str) -> None:
    from uuid import uuid4

    tokens = payload.get("tokensConsumed") if isinstance(payload, dict) else None
    left = payload.get("tokensLeft") if isinstance(payload, dict) else None
    refill_in = payload.get("refillIn") if isinstance(payload, dict) else None
    refill_rate = payload.get("refillRate") if isinstance(payload, dict) else None
    con.execute(
        """
        INSERT INTO amazon_request(
          request_id, batch_id, requested_at, endpoint, sanitized_params_json, http_status,
          tokens_consumed, tokens_left, refill_in, refill_rate, error_redacted
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "req_" + uuid4().hex[:24],
            batch_id,
            now,
            ENDPOINT,
            json.dumps(sanitized, ensure_ascii=False, sort_keys=True),
            status,
            tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else None,
            left if isinstance(left, int) and not isinstance(left, bool) else None,
            refill_in if isinstance(refill_in, int) and not isinstance(refill_in, bool) else None,
            refill_rate if isinstance(refill_rate, int) and not isinstance(refill_rate, bool) else None,
            error_text,
        ),
    )
