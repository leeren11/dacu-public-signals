from __future__ import annotations

import hashlib
import json
import re

# Field names only. tokensConsumed / tokensLeft are Keepa response counters, not credentials.
_SECRET_NORM = {
    "key",
    "apikey",
    "acceskey",
    "accesskey",
    "secret",
    "password",
    "authorization",
    "keepaapikey",
    "token",
}
_QUERY_SECRET = re.compile(
    r"(?i)(key|api_key|api-key|token|secret|password|authorization)=([^&\s\"']+)"
)


def norm_field(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj: object) -> str:
    return sha256_hex(canonical_bytes(obj))


def text_secret_count(text: str) -> int:
    return len(_QUERY_SECRET.findall(text))


def redact_text(text: str, extra_secrets: list[str] | None = None) -> str:
    out = _QUERY_SECRET.sub(r"\1=[REDACTED]", text)
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(secret, "[REDACTED]")
    return out


def redact_obj(obj: object, counter: list[int] | None = None) -> object:
    """Return a copy with credential fields and query-string secrets removed."""
    box = counter if counter is not None else [0]
    return _walk(obj, box)


def _walk(obj: object, counter: list[int]) -> object:
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if norm_field(key) in _SECRET_NORM:
                out[key] = "[REDACTED]"
                counter[0] += 1
            else:
                out[key] = _walk(value, counter)
        return out
    if isinstance(obj, list):
        return [_walk(item, counter) for item in obj]
    if isinstance(obj, str):
        red = redact_text(obj)
        if red != obj:
            counter[0] += 1
        return red
    return obj
