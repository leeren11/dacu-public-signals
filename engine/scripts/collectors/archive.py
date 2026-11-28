"""Parseable response archives.

The previous cache writer sliced a JSON string at 2_000_000 characters and the
raw dump sliced the body at 80_000 characters before appending a 16-character
marker. Those cuts produced invalid JSON of about 2MB and raw files of 80016
characters. A sliced file is not a valid source.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ARCHIVE_JSON_CHAR_CAP = 8_000_000
BODY_PREFIX_CHARS = 200


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def build_cache_payload(data: dict, *, char_cap: int = ARCHIVE_JSON_CHAR_CAP) -> dict:
    """Return a JSON-serializable payload. Oversized bodies are not sliced in place."""
    payload = dict(data)
    body = payload.get("body") or ""
    if not isinstance(body, str):
        body = str(body)
        payload["body"] = body
    digest = sha256_text(body)
    nbytes = len(body.encode("utf-8"))
    payload["body_sha256"] = digest
    payload["body_bytes"] = nbytes
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) <= char_cap:
        payload["truncated"] = 0
        payload["saved_bytes"] = nbytes
        payload["archive_status"] = "complete"
        return payload
    payload.pop("body", None)
    payload["truncated"] = 1
    payload["saved_bytes"] = 0
    payload["body_prefix"] = body[:BODY_PREFIX_CHARS]
    payload["archive_status"] = "truncated_manifest"
    return payload


def pointer_manifest(payload: dict, cache_name: str) -> dict:
    keys = (
        "url", "fetched_at", "http_status", "error", "from_cache", "transport",
        "body_sha256", "body_bytes", "saved_bytes", "truncated", "archive_status",
        "body_prefix",
    )
    manifest = {key: payload[key] for key in keys if key in payload}
    manifest["cache_file"] = cache_name
    manifest["body_embedded"] = 0
    return manifest


def write_json_atomic(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    json.loads(text)
    atomic_write_text(path, text)


def classify_cache_file(path: Path) -> dict:
    """Describe a cache file without treating a damaged or truncated file as a source."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"path": str(path), "valid_source": False, "status": "unreadable", "reason": str(exc)}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return {
            "path": str(path),
            "valid_source": False,
            "status": "legacy_truncated_invalid",
            "reason": str(exc),
            "bytes": path.stat().st_size,
        }
    if not isinstance(data, dict):
        return {"path": str(path), "valid_source": False, "status": "not_an_object", "reason": type(data).__name__}
    if data.get("truncated") or data.get("archive_status") == "truncated_manifest":
        return {"path": str(path), "valid_source": False, "status": "truncated_manifest", "reason": "body omitted; hash kept"}
    body = data.get("body")
    if data.get("body_sha256") and isinstance(body, str):
        if sha256_text(body) != data["body_sha256"]:
            return {"path": str(path), "valid_source": False, "status": "hash_mismatch", "reason": "body does not match body_sha256"}
    if isinstance(body, str) and body.endswith("\n/* truncated */"):
        return {"path": str(path), "valid_source": False, "status": "legacy_body_marker", "reason": "sliced body marker is not the response"}
    if data.get("http_status") in (200, 201) and isinstance(body, str) and body:
        return {"path": str(path), "valid_source": True, "status": "complete", "reason": ""}
    return {"path": str(path), "valid_source": False, "status": "incomplete", "reason": "missing body or non-success status"}
