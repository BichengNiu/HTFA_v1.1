"""Apply approved indicator retirements to a candidate pair and prove retained data unchanged."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

import duckdb

from . import db
from .history_validation import quote, report_columns
from .paths import DB_PATH, WORKBOOK_PATH
from .publish_report import publish_workbook
from .retired_sources import (
    RETIRED_EXTRA_SHEETS, RETIRED_INDICATORS, RETIRED_TABLES,
    retire_database, retire_workbook,
)
from .source_registry import RETIRED_SOURCES


def retired_sheet_names():
    return {sheet for _, sheet in RETIRED_SOURCES.values()} | set(RETIRED_EXTRA_SHEETS)


def validate_pruning(before, after):
    """Reject any data change outside the explicit retirement table/indicator scope.

    Unlike normal refresh validation this migration permits approved removals.
    Every retained fact, including all energy source facts, must match exactly.
    Published values are compared by sheet, indicator, duplicate occurrence and
    date, so workbook column shifts cannot hide an accidental deletion.
    """
    retired_tables = set(RETIRED_TABLES) | {table for table, _ in RETIRED_SOURCES.values()}
    # Legacy aliases belong to the same retired detail table.
    retired_tables |= {name.split('.', 1)[-1] for name in retired_tables}
    metadata = {"meta_indicator_dictionary", "meta_column_dictionary", "meta_retired_indicators"}
    checked = energy = 0
    with duckdb.connect(":memory:") as con:
        for alias, path in (("previous", before), ("candidate", after)):
            escaped = str(Path(path).resolve()).replace("'", "''")
            con.execute(f"ATTACH '{escaped}' AS {alias} (READ_ONLY)")
        # The audit allowlist comes from approved source code, never from the
        # candidate's editable metadata: misclassifying a kept indicator must
        # not turn its deletion into an authorized change.
        con.execute("CREATE TEMP TABLE allowed_fact_indicators(table_name VARCHAR, indicator VARCHAR)")
        scoped = [(table, name) for table, sheet in (
            ("cbuae_monthly", "月度_CBUAE"),
            ("dubai_airway_bill_monthly", "月度_迪拜海关航空"),
        ) for name in RETIRED_INDICATORS.get(sheet, ())]
        con.executemany("INSERT INTO allowed_fact_indicators VALUES (?,?)", scoped)
        tables = con.execute("SELECT table_schema,table_name FROM information_schema.tables "
                             "WHERE table_catalog='previous' AND table_schema NOT IN ('report','information_schema','pg_catalog')").fetchall()
        for schema, table in tables:
            name = f"{schema}.{table}"
            target = f"{quote(schema)}.{quote(table)}"
            if name in retired_tables or (schema == "main" and table in retired_tables):
                if con.execute("SELECT 1 FROM information_schema.tables WHERE table_catalog='candidate' AND table_schema=? AND table_name=?", [schema, table]).fetchone():
                    raise ValueError(f"Retired table returned: {name}")
                continue
            if schema == "main" and table in metadata:
                continue
            if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_catalog='candidate' AND table_schema=? AND table_name=?", [schema, table]).fetchone():
                raise ValueError(f"Retained table removed: {name}")
            clause = ""
            if schema == "main" and table in {"cbuae_monthly", "dubai_airway_bill_monthly"}:
                clause = f" WHERE indicator NOT IN (SELECT indicator FROM allowed_fact_indicators WHERE table_name='{table}')"
            elif schema == "main" and table == "foreign_labour_monthly":
                clause = " WHERE series IN ('nepal_with_reentry','bangladesh_clearance')"
            elif schema == "main" and table == "ded_monthly":
                clause = " WHERE series NOT IN ('records','official_new_licenses')"
            old = f"SELECT * FROM previous.{target}{clause}"
            new = f"SELECT * FROM candidate.{target}"
            changed = con.execute(f"SELECT count(*) FROM (({old} EXCEPT ALL {new}) UNION ALL ({new} EXCEPT ALL {old}))").fetchone()[0]
            if changed:
                raise ValueError(f"Retained facts changed: {name}: {changed}")
            checked += 1
            energy += schema == "energy_supply"
        report_columns(con, "previous", "old_columns")
        report_columns(con, "candidate", "new_columns")
        con.execute("DELETE FROM old_columns WHERE sheet_index=0")
        con.execute("DELETE FROM new_columns WHERE sheet_index=0")
        allowed = [(s, n) for s, names in RETIRED_INDICATORS.items() for n in names]
        con.execute("CREATE TEMP TABLE retired_columns(sheet VARCHAR, indicator VARCHAR)")
        if allowed:
            con.executemany("INSERT INTO retired_columns VALUES (?,?)", allowed)
        con.execute("CREATE TEMP TABLE retired_sheets(sheet VARCHAR)")
        con.executemany("INSERT INTO retired_sheets VALUES (?)", [(s,) for s in retired_sheet_names()])
        retained = "sheet NOT IN (SELECT sheet FROM retired_sheets) AND NOT EXISTS (SELECT 1 FROM retired_columns r WHERE r.sheet=o.sheet AND r.indicator=o.indicator)"
        con.execute(f"CREATE TEMP TABLE expected_columns AS SELECT * FROM old_columns o WHERE {retained}")
        old = "SELECT sheet,indicator,occurrence FROM expected_columns"
        new = "SELECT sheet,indicator,occurrence FROM new_columns"
        if con.execute(f"SELECT count(*) FROM (({old} EXCEPT ALL {new}) UNION ALL ({new} EXCEPT ALL {old}))").fetchone()[0]:
            raise ValueError("Retained report column set changed")
        old = "SELECT c.sheet,c.indicator,c.occurrence,o.period,o.value FROM previous.report.observations o JOIN expected_columns c USING(sheet_index,column_index)"
        new = "SELECT c.sheet,c.indicator,c.occurrence,o.period,o.value FROM candidate.report.observations o JOIN new_columns c USING(sheet_index,column_index)"
        if con.execute(f"SELECT count(*) FROM (({old} EXCEPT ALL {new}) UNION ALL ({new} EXCEPT ALL {old}))").fetchone()[0]:
            raise ValueError("Retained published observations changed")
        old_count = con.execute("SELECT count(*) FROM old_columns").fetchone()[0]
        kept_count = con.execute("SELECT count(*) FROM new_columns").fetchone()[0]
        values = con.execute("SELECT count(*) FROM candidate.report.observations").fetchone()[0]
    return {"status": "ok", "retained_tables_checked": checked,
            "energy_tables_unchanged": energy, "indicators_before": old_count,
            "indicators_retained": kept_count, "indicators_removed": old_count-kept_count,
            "retained_published_observations": values}


def run(*, database=DB_PATH, workbook=WORKBOOK_PATH, publish=False):
    """Prune only a candidate, validate against the originals, then install atomically."""
    from htfa.monitoring.energy_supply.jobs.publish import publication_lock, install_pair

    database, workbook = Path(database).resolve(), Path(workbook).resolve()
    with publication_lock(database), tempfile.TemporaryDirectory(prefix="prune-candidate-", dir=database.parent) as temp:
        candidate = Path(temp) / database.name
        next_workbook = Path(temp) / workbook.name
        shutil.copy2(database, candidate)
        shutil.copy2(workbook, next_workbook)
        with db.connect(candidate) as con:
            retire_database(con)
        removed = retire_workbook(next_workbook, database=candidate)
        with db.connect(candidate) as con:
            report = publish_workbook(con, next_workbook)
        validation = validate_pruning(database, candidate)
        if publish:
            install_pair(candidate, next_workbook, database, workbook)
        return {"installed": publish, "removed": removed, "report": report, "validation": validation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(publish=args.publish), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
