"""Reject loss of archived observation keys or published report histories."""

import json

import duckdb


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def observation_tables(con, catalog):
    """Find dated, primary-keyed source tables; exclude logs and dictionaries."""
    rows = con.execute(
        "SELECT schema_name,table_name,constraint_column_names FROM duckdb_constraints() "
        "WHERE database_name=? AND constraint_type='PRIMARY KEY' "
        "AND schema_name IN ('main','detail','dld','energy_supply')", [catalog],
    ).fetchall()
    return [(schema, table, keys) for schema, table, keys in rows
            if (schema == "energy_supply" and table in {"ais_reports", "portwatch_daily", "sea_entries"})
            or (schema != "energy_supply" and set(keys) & {"period", "date", "month", "week_end", "year", "quarter"})]


def report_columns(con, catalog, target):
    """Map columns by sheet/name/duplicate occurrence, independent of positions."""
    rows = []
    for index, name, heading, width in con.execute(
        f"SELECT sheet_index,sheet_name,heading,column_count FROM {catalog}.report.sheets"
    ).fetchall():
        header = json.loads(heading)
        if len(header) < 2:
            continue
        occurrences = {}
        for column in range(1, width):
            indicator = header[1][column]
            if indicator is None:
                continue
            occurrences[indicator] = occurrences.get(indicator, 0) + 1
            rows.append((index, column, name, indicator, occurrences[indicator]))
    con.execute(f"CREATE TEMP TABLE {target} (sheet_index INT,column_index INT,sheet VARCHAR,indicator VARCHAR,occurrence INT)")
    if rows:
        con.executemany(f"INSERT INTO {target} VALUES (?,?,?,?,?)", rows)


def validate_history(before, after, *, include_report=False):
    """Permit additions/revisions, reject removed keys and numeric-to-null loss."""
    checked = 0
    with duckdb.connect(":memory:") as con:
        before_sql = str(before).replace("'", "''")
        after_sql = str(after).replace("'", "''")
        con.execute(f"ATTACH '{before_sql}' AS previous (READ_ONLY)")
        con.execute(f"ATTACH '{after_sql}' AS candidate (READ_ONLY)")
        for schema, table, keys in observation_tables(con, "previous"):
            name = quote(schema) + "." + quote(table)
            if not con.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_catalog='candidate' AND table_schema=? AND table_name=?",
                [schema, table],
            ).fetchone():
                raise ValueError(f"History table removed: {schema}.{table}")
            columns = con.execute(f"DESCRIBE previous.{name}").fetchall()
            matches = " AND ".join(f"o.{quote(key)} IS NOT DISTINCT FROM n.{quote(key)}" for key in keys)
            lost = con.execute(
                f"SELECT COUNT(*) FROM previous.{name} o WHERE NOT EXISTS "
                f"(SELECT 1 FROM candidate.{name} n WHERE {matches})"
            ).fetchone()[0]
            if lost:
                raise ValueError(f"History keys removed: {schema}.{table}: {lost}")
            numeric = [column for column, kind, *_ in columns if column not in keys and
                       kind.split('(')[0] in {"DECIMAL", "DOUBLE", "FLOAT", "BIGINT", "INTEGER", "SMALLINT", "TINYINT", "HUGEINT", "UBIGINT", "UINTEGER"}]
            if numeric:
                erased = " OR ".join(f"(o.{quote(column)} IS NOT NULL AND n.{quote(column)} IS NULL)" for column in numeric)
                if con.execute(
                    f"SELECT COUNT(*) FROM previous.{name} o JOIN candidate.{name} n ON {matches} WHERE {erased}"
                ).fetchone()[0]:
                    raise ValueError(f"Historical numeric values erased: {schema}.{table}")
            checked += 1
        if include_report:
            report_columns(con, "previous", "old_columns")
            report_columns(con, "candidate", "new_columns")
            lost = con.execute("""
                WITH old_values AS (
                    SELECT c.sheet,c.indicator,c.occurrence,o.period
                    FROM previous.report.observations o JOIN old_columns c USING(sheet_index,column_index)
                ), new_values AS (
                    SELECT c.sheet,c.indicator,c.occurrence,o.period
                    FROM candidate.report.observations o JOIN new_columns c USING(sheet_index,column_index)
                )
                SELECT COUNT(*) FROM (SELECT * FROM old_values EXCEPT SELECT * FROM new_values)
            """).fetchone()[0]
            if lost:
                raise ValueError(f"Published historical observations removed: {lost}")
    return {"status": "ok", "source_tables_checked": checked, "report_checked": include_report}
