"""CLI for the shadow evidence layer. It does not start the daily pipeline."""

from __future__ import annotations

import argparse
import json

from evidence_v2.shadow import run_fixture, score_manifest
from evidence_v2.store import connect, load_fixture, migrate
from evidence_v2.timebox import parse_aware


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="evidence_research_v2 shadow ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    migrate_cmd = sub.add_parser("migrate", help="apply additive v7 tables")
    migrate_cmd.add_argument("--db", required=True)

    run_cmd = sub.add_parser("run", help="ingest a labeled fixture and write one shadow manifest")
    run_cmd.add_argument("--db", required=True)
    run_cmd.add_argument("--fixture", required=True)
    run_cmd.add_argument("--cutoff", help="aware ISO cutoff; default is the fixture replay_cutoff")

    replay_cmd = sub.add_parser("replay", help="score an existing plan at a cutoff")
    replay_cmd.add_argument("--db", required=True)
    replay_cmd.add_argument("--plan-id", required=True)
    replay_cmd.add_argument("--cutoff", required=True)

    args = parser.parse_args(argv)
    con = connect(args.db)
    try:
        migrate(con)
        if args.command == "migrate":
            print(json.dumps({"schema_version": "7", "accuracy_claim": None}, ensure_ascii=False))
            return 0
        if args.command == "run":
            document = load_fixture(args.fixture)
            result = run_fixture(con, document, args.cutoff)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        cutoff = parse_aware(args.cutoff)
        if cutoff is None:
            raise SystemExit("cutoff must be an aware timestamp")
        result = score_manifest(con, args.plan_id, cutoff)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        con.close()
