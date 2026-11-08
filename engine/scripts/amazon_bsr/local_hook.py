"""Optional daily hook. Local files only. Never calls Keepa and never scores."""

from __future__ import annotations

from pathlib import Path

from amazon_bsr.db import connect_rw
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.ingest import import_keepa_file


def ingest_local_file(db_path, file_path, *, retrieved_at: str | None = None, now: str | None = None) -> dict:
    text = str(file_path)
    lowered = text.lower()
    if "://" in text or lowered.startswith("http:") or lowered.startswith("https:"):
        raise AmazonBsrError(
            "live_forbidden",
            "the daily hook accepts a local Keepa file only and does not make live requests",
        )
    path = Path(file_path)
    if not path.is_file():
        raise AmazonBsrError("local_file_missing", f"{path} is not a local file")
    con = connect_rw(db_path, create=False)
    try:
        return import_keepa_file(
            con,
            path,
            source_kind="offline_file",
            domain_id=1,
            retrieved_at=retrieved_at,
            allow_example=False,
            now=now,
        )
    finally:
        con.close()
