"""Operator CLI. It does not start the daily pipeline and does not score SKUs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from collectors.archive import classify_cache_file
from youtube_official_feed.http import Exchange
from youtube_official_feed.parse import official_url
from youtube_official_feed.store import (
    approve_watchlist,
    connect,
    import_xml,
    load_json,
    migrate,
    purge_expired,
    record_fetch,
    rollback,
)


def _urllib_transport(channel_id: str):
    import urllib.error
    import urllib.request

    def transport(url: str, headers: dict) -> Exchange:
        if url != official_url(channel_id):
            raise ValueError("refusing a non-official URL")
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                final = response.geturl()
                if final != url:
                    return Exchange(status=response.status, final_url=final, error="redirect")
                body = response.read().decode("utf-8", errors="replace")
                return Exchange(
                    status=response.status,
                    body=body,
                    content_type=response.headers.get("Content-Type", ""),
                    headers={key: value for key, value in response.headers.items()},
                    final_url=final,
                    etag=response.headers.get("ETag"),
                )
        except urllib.error.HTTPError as exc:
            return Exchange(
                status=exc.code,
                body=exc.read().decode("utf-8", errors="replace"),
                content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
                headers={key: value for key, value in (exc.headers.items() if exc.headers else [])},
                final_url=url,
                error=f"HTTP {exc.code}",
            )
        except TimeoutError:
            raise
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower():
                raise TimeoutError(str(exc)) from exc
            return Exchange(status=None, error=str(exc), final_url=url)

    return transport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="youtube_official_feed_v1 shadow ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    migrate_cmd = sub.add_parser("migrate")
    migrate_cmd.add_argument("--db", required=True)
    approve = sub.add_parser("approve-watchlist")
    approve.add_argument("--db", required=True)
    approve.add_argument("--watchlist", required=True)
    import_cmd = sub.add_parser("import-xml")
    import_cmd.add_argument("--db", required=True)
    import_cmd.add_argument("--xml", required=True)
    import_cmd.add_argument("--channel-id", required=True)
    import_cmd.add_argument("--watchlist-version", required=True)
    import_cmd.add_argument("--retrieved-at", required=True)
    import_cmd.add_argument("--now", required=True)
    import_cmd.add_argument("--archive-dir", required=True)
    import_cmd.add_argument("--example-label", required=True)
    fetch_cmd = sub.add_parser("fetch")
    fetch_cmd.add_argument("--db", required=True)
    fetch_cmd.add_argument("--channel-id", required=True)
    fetch_cmd.add_argument("--watchlist-version", required=True)
    fetch_cmd.add_argument("--now", required=True)
    fetch_cmd.add_argument("--archive-dir", required=True)
    fetch_cmd.add_argument("--example-label", required=True)
    purge = sub.add_parser("purge-expired")
    purge.add_argument("--db", required=True)
    purge.add_argument("--now", required=True)
    inspect = sub.add_parser("inspect-cache")
    inspect.add_argument("--path", required=True)
    disabled = sub.add_parser("disabled")
    disabled.add_argument("--db", required=True)
    back = sub.add_parser("rollback")
    back.add_argument("--db", required=True)
    args = parser.parse_args(argv)
    if args.command == "inspect-cache":
        print(json.dumps(classify_cache_file(Path(args.path)), ensure_ascii=False))
        return 0
    connection = connect(args.db)
    try:
        migrate(connection)
        if args.command == "migrate":
            print(json.dumps({"schema_version": "8", "scores_written": False}, ensure_ascii=False))
            return 0
        if args.command == "rollback":
            rollback(connection)
            print(json.dumps({"rolled_back": "youtube_feed_*", "director_v1": "untouched"}, ensure_ascii=False))
            return 0
        if args.command == "disabled":
            rows = [dict(row) for row in connection.execute("SELECT * FROM youtube_feed_disabled_source ORDER BY source_id")]
            print(json.dumps({"disabled": rows, "live_fetch": False}, ensure_ascii=False))
            return 0
        if args.command == "approve-watchlist":
            version = approve_watchlist(connection, load_json(args.watchlist))
            print(json.dumps({"watchlist_version": version, "maps_to_sku": 0}, ensure_ascii=False))
            return 0
        if args.command == "import-xml":
            evidence_id = import_xml(
                connection,
                xml_text=Path(args.xml).read_text(encoding="utf-8"),
                channel_id=args.channel_id,
                watchlist_version=args.watchlist_version,
                retrieved_at=args.retrieved_at,
                now=args.now,
                archive_dir=Path(args.archive_dir),
                example_label=args.example_label,
            )
            print(json.dumps({"evidence_id": evidence_id, "not_for_scoring": True}, ensure_ascii=False))
            return 0
        if args.command == "fetch":
            result = record_fetch(
                connection,
                channel_id=args.channel_id,
                watchlist_version=args.watchlist_version,
                transport=_urllib_transport(args.channel_id),
                now=args.now,
                archive_dir=Path(args.archive_dir),
                example_label=args.example_label,
            )
            result["continuous_verification"] = False
            result["not_for_scoring"] = True
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "purge-expired":
            removed = purge_expired(connection, args.now)
            print(json.dumps({"removed_evidence": removed, "retention_max_days": 30}, ensure_ascii=False))
            return 0
    finally:
        connection.close()
    return 2
