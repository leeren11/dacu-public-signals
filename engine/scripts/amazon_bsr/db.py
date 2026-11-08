"""SQLite migration, connection, and same-machine backup for the Amazon layer.

A backup written beside the database uses SQLite's online backup API and is
checked with integrity_check plus a sha256 of the copy. It is not an offsite copy.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

from amazon_bsr import SCHEMA_VERSION
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.policies import DOMAIN_US, POOL_MAX, POOL_MIN, POOL_NOTE, TARGET_GROUPS, policy_json, pool_status_for
from amazon_bsr.redact import sha256_hex
from amazon_bsr.timeutil import now_utc

SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "migrate_v6_amazon_bsr.sql"
GZIP_THRESHOLD = 8192
SOURCE_ID = "keepa"
DOCS_URL = "https://keepa.com/api-docs/product-object.html"
LICENSE_NOTE = (
    "Subject to the operator's own Keepa license. This repository does not grant "
    "redistribution rights. Raw public export is off by default."
)
LAYER_NOTE = (
    "Independent Amazon BSR evidence. Not an input to Live_Rolling_Score, prediction freezes, "
    "or the 2026-11-12 and 2026-12-01 walk-forward weights. "
    "ln(old_bsr/new_bsr) and rank-improvement percent are not sales growth. "
    "csv[17] COUNT_REVIEWS is the rating count, not the written review count. "
    "An empty ASIN pool is needs_input. A backup created here is not offsite."
)


class transaction:
    """Explicit SQL transaction. Nested calls join the transaction already open."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.own = False

    def __enter__(self) -> sqlite3.Connection:
        self.own = not self.con.in_transaction
        if self.own:
            self.con.execute("BEGIN")
        return self.con

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.own:
            return False
        if exc_type is None:
            self.con.commit()
        else:
            self.con.rollback()
        return False


def connect_rw(path: Path | str, *, create: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if not create and (not path.exists() or path.stat().st_size == 0):
        raise AmazonBsrError("db_missing", f"{path} does not exist; run migrate against the existing signal database")
    if not path.parent.exists():
        raise AmazonBsrError("db_directory_missing", f"{path.parent} does not exist")
    con = sqlite3.connect(path, isolation_level=None)
    return _prepare(con)


def connect_ro(path: Path | str) -> sqlite3.Connection:
    path = Path(path).resolve()
    if not path.exists() or path.stat().st_size == 0:
        raise AmazonBsrError("db_missing", f"{path} does not exist")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, isolation_level=None)
    return _prepare(con)


def _prepare(con: sqlite3.Connection) -> sqlite3.Connection:
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def pack_payload(data: bytes) -> tuple[str, bytes]:
    if len(data) > GZIP_THRESHOLD:
        return "gzip_json", gzip.compress(data, compresslevel=9)
    return "utf8_json", data


def unpack_payload(encoding: str, blob: bytes | str) -> bytes:
    if isinstance(blob, str):
        blob = blob.encode("utf-8")
    if encoding == "gzip_json":
        return gzip.decompress(blob)
    if encoding == "utf8_json":
        return blob
    raise AmazonBsrError("payload_encoding", f"unknown payload encoding {encoding}")


def integrity_and_hash(path: Path) -> tuple[str, str]:
    con = sqlite3.connect(path)
    try:
        row = con.execute("PRAGMA integrity_check").fetchone()
        status = row[0] if row else "missing"
    finally:
        con.close()
    return status, sha256_hex(path.read_bytes())


def backup_database(src: Path | str, dest: Path | str) -> dict:
    """Copy src with the SQLite backup API, then check integrity and hash the copy."""
    src = Path(src)
    dest = Path(dest)
    if not src.exists() or src.stat().st_size == 0:
        raise AmazonBsrError("db_missing", f"nothing to back up at {src}")
    if dest.exists():
        raise AmazonBsrError("backup_exists", f"refusing to overwrite {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        # pages=-1 copies the whole database and returns None. A positive page
        # count returns a context manager; this call is the one-step form.
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    status, digest = integrity_and_hash(dest)
    if status != "ok":
        raise AmazonBsrError("backup_integrity", f"backup integrity_check returned {status}")
    sidecar = Path(str(dest) + ".sha256")
    sidecar.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    return {
        "backup_path": str(dest),
        "sha256": digest,
        "sha256_path": str(sidecar),
        "integrity_check": "ok",
        "method": "sqlite_backup_api",
        "same_machine_copy": True,
        "offsite": False,
        "note_zh": "这次备份用 SQLite backup API 写在本机路径上，并通过了 integrity_check。它不是异地备份。",
    }


def _table_names(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def inspect_database(path: Path | str) -> dict:
    path = Path(path)
    group_names = [row["sku_cluster"] for row in TARGET_GROUPS]
    if not path.exists() or path.stat().st_size == 0:
        return {
            "exists": path.exists(),
            "applied": False,
            "missing_groups": group_names,
            "has_tables": False,
            "source": False,
            "existing_tables": [],
        }
    con = connect_ro(path)
    try:
        tables = _table_names(con)
        applied = False
        if "schema_migrations" in tables:
            applied = (
                con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    (SCHEMA_VERSION,),
                ).fetchone()
                is not None
            )
        missing = list(group_names)
        if "amazon_target_group" in tables:
            have = {row[0] for row in con.execute("SELECT sku_cluster FROM amazon_target_group")}
            missing = [name for name in group_names if name not in have]
        source = False
        if "amazon_source" in tables:
            source = con.execute("SELECT 1 FROM amazon_source WHERE source_id = ?", (SOURCE_ID,)).fetchone() is not None
        return {
            "exists": True,
            "applied": applied,
            "missing_groups": missing,
            "has_tables": bool(tables),
            "source": source,
            "existing_tables": tables,
        }
    finally:
        con.close()


def seed(con: sqlite3.Connection, recorded_at: str) -> None:
    # Supply applied_at. INSERT OR IGNORE of version alone is a no-op when an
    # older schema_migrations table has applied_at NOT NULL and no default.
    con.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, recorded_at),
    )
    con.execute(
        """
        INSERT OR IGNORE INTO amazon_source(source_id, source_name, docs_url, license_note)
        VALUES (?, 'Keepa', ?, ?)
        """,
        (SOURCE_ID, DOCS_URL, LICENSE_NOTE),
    )
    con.execute(
        "INSERT OR IGNORE INTO amazon_layer_note(note_id, note) VALUES (?, ?)",
        (SCHEMA_VERSION, LAYER_NOTE),
    )
    for group in TARGET_GROUPS:
        con.execute(
            """
            INSERT OR IGNORE INTO amazon_target_group(
              sku_cluster, domain_id, display_zh, attribute_policy_json,
              recommended_pool_min, recommended_pool_max, pool_status, pool_count, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                group["sku_cluster"],
                DOMAIN_US,
                group["display_zh"],
                policy_json(group),
                POOL_MIN,
                POOL_MAX,
                pool_status_for(0),
                POOL_NOTE,
                recorded_at,
            ),
        )


def refresh_pool_counts(con: sqlite3.Connection, updated_at: str) -> list[dict]:
    rows = []
    for group in TARGET_GROUPS:
        count = con.execute(
            """
            SELECT COUNT(*) FROM amazon_asin_map
            WHERE sku_cluster = ? AND domain_id = 1 AND is_current = 1
            """,
            (group["sku_cluster"],),
        ).fetchone()[0]
        status = pool_status_for(count)
        con.execute(
            """
            UPDATE amazon_target_group
            SET pool_count = ?, pool_status = ?, updated_at = ?
            WHERE sku_cluster = ?
            """,
            (count, status, updated_at, group["sku_cluster"]),
        )
        rows.append({"sku_cluster": group["sku_cluster"], "pool_count": count, "pool_status": status})
    return rows


def require_migrated(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if row is None:
        raise AmazonBsrError("migration_required", "schema_migrations is missing; run amazon_bsr_cli.py migrate")
    found = con.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (SCHEMA_VERSION,),
    ).fetchone()
    if found is None:
        raise AmazonBsrError("migration_required", "amazon_bsr_v1 is not in schema_migrations; run migrate before import")
    count = con.execute("SELECT COUNT(*) FROM amazon_target_group").fetchone()[0]
    if count < len(TARGET_GROUPS):
        raise AmazonBsrError("migration_required", "Amazon target groups are missing; run migrate again to seed them")


def migrate_database(
    path: Path | str,
    *,
    dry_run: bool = False,
    backup_dir: Path | str | None = None,
    now: str | None = None,
) -> dict:
    path = Path(path)
    if not path.parent.exists():
        raise AmazonBsrError("db_directory_missing", f"{path.parent} does not exist")
    recorded_at = now or now_utc()
    state = inspect_database(path)
    base = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "dry_run": dry_run,
        "existing_tables": state["existing_tables"],
        "drops": [],
        "offsite": False,
        "preserves_existing_tables": True,
    }
    if state["applied"] and not state["missing_groups"] and state["source"]:
        return {**base, "status": "already_applied", "backup": None, "wrote": False}
    if dry_run:
        return {
            **base,
            "status": "dry_run",
            "backup": None,
            "wrote": False,
            "would_apply_sql": not state["applied"],
            "would_seed_groups": state["missing_groups"],
            "would_backup": bool(state["exists"] and state["has_tables"] and not state["applied"]),
        }
    backup_info = None
    if state["exists"] and state["has_tables"] and not state["applied"]:
        directory = Path(backup_dir) if backup_dir else path.parent / "backups"
        stamp = recorded_at.replace("-", "").replace(":", "")
        dest = directory / f"{path.name}.bak-{SCHEMA_VERSION}-{stamp}"
        backup_info = backup_database(path, dest)
    con = connect_rw(path, create=True)
    try:
        if not state["applied"]:
            script = SQL_PATH.read_text(encoding="utf-8")
            try:
                con.executescript(script)
            except Exception:
                if con.in_transaction:
                    con.rollback()
                raise
        con.execute("BEGIN")
        seed(con, recorded_at)
        con.commit()
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
    return {
        **base,
        "status": "applied",
        "backup": backup_info,
        "wrote": True,
        "note_zh": "迁移只新增 amazon_* 表。旧表没有删除。备份若生成，也只在本机。",
    }
