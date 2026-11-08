"""Command line for migrate, import, derive, health, and the explicit live fetch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from amazon_bsr.db import backup_database, connect_ro, connect_rw, migrate_database
from amazon_bsr.derive import derive_metrics
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.ingest import import_keepa_file
from amazon_bsr.live import live_fetch
from amazon_bsr.mapping import import_mapping, load_mapping_file, template_document
from amazon_bsr.report import export_summary, health_report, status_report
from amazon_bsr.timeutil import now_utc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amazon_bsr_cli.py",
        description="Independent Amazon BSR evidence layer. Does not change Live scores or freezes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="add amazon_* tables; backs up an existing database first")
    _db(migrate)
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--backup-dir")

    backup = sub.add_parser("backup", help="SQLite online backup, integrity check, and sha256")
    _db(backup)
    backup.add_argument("--dest", required=True)

    template = sub.add_parser("mapping-template", help="write an empty ASIN-pool template")
    template.add_argument("--out")

    mapping = sub.add_parser("mapping-import", help="import a versioned sku_cluster to ASIN file")
    _db(mapping)
    mapping.add_argument("--file", required=True)
    mapping.add_argument("--dry-run", action="store_true")
    mapping.add_argument("--backup-dir")

    raw = sub.add_parser("import-raw", help="import a local Keepa JSON or JSONL file")
    _db(raw)
    raw.add_argument("--file", required=True)
    raw.add_argument("--domain", type=int, required=True)
    raw.add_argument("--retrieved-at")
    raw.add_argument("--known-since")
    raw.add_argument("--known-since-reason")
    raw.add_argument("--license-note")
    raw.add_argument("--dry-run", action="store_true")

    derive = sub.add_parser("derive", help="compute 7-day rank and count metrics")
    _db(derive)
    derive.add_argument("--as-of", help="UTC date YYYY-MM-DD")
    derive.add_argument("--selection-cutoff", help="UTC timestamp; default is now and is not a freeze replay")
    derive.add_argument("--eval-freeze-id", help="label only; this command does not read freeze tables")
    derive.add_argument("--eval-date")
    derive.add_argument("--dry-run", action="store_true")

    status = sub.add_parser("status", help="pool, counts, and source freshness")
    _db(status)
    health = sub.add_parser("health", help="status plus integrity_check")
    _db(health)

    export = sub.add_parser("export", help="write an Amazon summary; raw payloads stay off unless requested")
    _db(export)
    export.add_argument("--out", required=True)
    export.add_argument("--include-raw", action="store_true")

    live = sub.add_parser("live-fetch", help="call Keepa only when --live-fetch and KEEPA_API_KEY are both present")
    _db(live)
    live.add_argument("--live-fetch", action="store_true")
    live.add_argument("--domain", type=int, required=True)
    live.add_argument("--asin", action="append", default=[])
    live.add_argument("--asin-file")
    live.add_argument("--token-budget", type=int, required=True)
    live.add_argument("--batch-size", type=int, required=True)
    live.add_argument("--days", type=int)
    live.add_argument("--stats-days", type=int)
    live.add_argument("--rating", action="store_true")
    live.add_argument("--offers", type=int)
    live.add_argument("--stock", action="store_true")
    live.add_argument("--buybox", action="store_true")
    live.add_argument("--update-hours", type=int)

    try:
        args = parser.parse_args(argv)
        result = _dispatch(args)
    except AmazonBsrError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False, sort_keys=True))
        return 2
    printed = dict(result)
    printed.pop("raw_payloads", None)
    if result.get("raw_included"):
        printed["stdout_omits_raw"] = True
    print(json.dumps(printed, ensure_ascii=False, sort_keys=True))
    if result.get("ok") is False:
        return 1
    return 0


def _db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", required=True, help="path to the SQLite file; not implied")


def _dispatch(args: argparse.Namespace) -> dict:
    if args.command == "migrate":
        return migrate_database(args.db, dry_run=args.dry_run, backup_dir=args.backup_dir)
    if args.command == "backup":
        return {"ok": True, **backup_database(args.db, args.dest)}
    if args.command == "mapping-template":
        document = template_document()
        wrote = None
        if args.out:
            dest = Path(args.out)
            if dest.exists():
                raise AmazonBsrError("output_exists", f"refusing to overwrite {dest}")
            dest.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            wrote = str(dest)
        return {"ok": True, "template": document, "wrote": wrote}
    if args.command == "mapping-import":
        if args.backup_dir and not args.dry_run:
            backup_database(args.db, Path(args.backup_dir) / (Path(args.db).name + ".before-mapping-import"))
        con = connect_rw(args.db, create=False)
        try:
            return import_mapping(con, load_mapping_file(Path(args.file)), dry_run=args.dry_run)
        finally:
            con.close()
    if args.command == "import-raw":
        con = connect_rw(args.db, create=False)
        try:
            return import_keepa_file(
                con,
                Path(args.file),
                domain_id=args.domain,
                retrieved_at=args.retrieved_at,
                known_since=args.known_since,
                known_since_reason=args.known_since_reason,
                license_note=args.license_note,
                dry_run=args.dry_run,
                allow_example=False,
            )
        finally:
            con.close()
    if args.command == "derive":
        explicit = args.selection_cutoff is not None
        cutoff = args.selection_cutoff or now_utc()
        con = connect_rw(args.db, create=False)
        try:
            result = derive_metrics(
                con,
                selection_cutoff=cutoff,
                as_of=args.as_of,
                eval_freeze_id=args.eval_freeze_id,
                eval_date=args.eval_date,
                allow_eval=explicit,
                dry_run=args.dry_run,
            )
        finally:
            con.close()
        result["selection_cutoff"] = cutoff
        result["historical_replay"] = explicit
        if not explicit:
            result["summary_zh"] = "未提供 selection-cutoff，本次按当前已知数据处理，不能当作冻结时点的回放。"
        return result
    if args.command == "status":
        con = connect_ro(args.db)
        try:
            return status_report(con)
        finally:
            con.close()
    if args.command == "health":
        con = connect_ro(args.db)
        try:
            return health_report(con)
        finally:
            con.close()
    if args.command == "export":
        dest = Path(args.out)
        if dest.exists():
            raise AmazonBsrError("output_exists", f"refusing to overwrite {dest}")
        con = connect_ro(args.db)
        try:
            body = export_summary(con, include_raw=args.include_raw)
        finally:
            con.close()
        dest.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return body
    if args.command == "live-fetch":
        if not args.live_fetch:
            raise AmazonBsrError("live_not_confirmed", "live-fetch does nothing until you also pass --live-fetch")
        return live_fetch(
            args.db,
            live_confirmed=True,
            asins=args.asin,
            asin_file=args.asin_file,
            domain_id=args.domain,
            token_budget=args.token_budget,
            batch_size=args.batch_size,
            days=args.days,
            stats_days=args.stats_days,
            rating=args.rating,
            offers=args.offers,
            stock=args.stock,
            buybox=args.buybox,
            update_hours=args.update_hours,
        )
    raise AmazonBsrError("usage", "unknown command")


if __name__ == "__main__":
    sys.exit(main())
