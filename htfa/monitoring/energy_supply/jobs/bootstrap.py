"""Import a verified upstream DuckDB snapshot into HTFA's energy schema."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

import duckdb

from htfa.monitoring.uae.jobs import db
from htfa.monitoring.uae.jobs.paths import DB_PATH
from htfa.monitoring.energy_supply.data.storage import SCHEMA

SOURCE_COMMIT = "72f3b04ba9205f66ec1b34231ec6ae3d927dfc9c"
SOURCE_SHA256 = "1e3c5b8007878a269c0c22f7d40a202065cd87e03cf9a5532dc4c120382e2154"
SOURCE_SIZE = 193212416


def import_snapshot(source: Path, destination: Path = DB_PATH) -> dict:
    """Validate and atomically import the fixed source; never replace existing facts."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if source.stat().st_size != SOURCE_SIZE or digest != SOURCE_SHA256:
        raise ValueError("能源保供源快照大小或 SHA256 不匹配")
    with duckdb.connect(str(destination)) as con:
        source_literal = str(source).replace("'", "''")
        con.execute(f"ATTACH '{source_literal}' AS energy_seed (READ_ONLY)")
        try:
            with db.transaction(con):
                existing = con.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='energy_supply'"
                ).fetchone()[0]
                if existing:
                    raise ValueError("能源保供 schema 已存在，禁止重复覆盖；请使用采集更新作业")
                con.execute("CREATE SCHEMA energy_supply")
                con.execute("SET schema='energy_supply'")
                con.execute(SCHEMA)
                tables = con.execute(
                    "SELECT table_name FROM duckdb_tables() "
                    "WHERE database_name='energy_seed' ORDER BY table_name"
                ).fetchall()
                counts = {}
                for (name,) in tables:
                    if not re.fullmatch(r"[a-z_]+", name):
                        raise ValueError(f"非法源表名：{name}")
                    con.execute(f'INSERT INTO energy_supply."{name}" SELECT * FROM energy_seed.main."{name}"')
                    actual = con.execute(f'SELECT count(*) FROM energy_supply."{name}"').fetchone()[0]
                    expected = con.execute(f'SELECT count(*) FROM energy_seed.main."{name}"').fetchone()[0]
                    if actual != expected:
                        raise ValueError(f"迁移记录数不一致：{name}")
                    counts[name] = actual
                con.execute(
                    "INSERT INTO app_meta VALUES ('htfa_import', ?)",
                    [f'{{"commit":"{SOURCE_COMMIT}","sha256":"{digest}"}}'],
                )
                # Preserve the reviewed port-type evidence used by the source
                # catalog and its provenance regression checks.
                audit = source.parents[1] / "audits/port_type_review_2026-10-16.json"
                if not audit.is_file():
                    raise FileNotFoundError(audit)
                from htfa.monitoring.energy_supply.data.storage import put_binary_document

                put_binary_document(
                    "audits/port_type_review_2026-10-16.json", audit.read_bytes(),
                    "application/json", conn=con,
                )
            return counts
        finally:
            con.execute("DETACH energy_seed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, default=DB_PATH)
    arguments = parser.parse_args()
    print(import_snapshot(arguments.source, arguments.destination))
