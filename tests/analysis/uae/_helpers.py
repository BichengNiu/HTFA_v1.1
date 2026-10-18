"""Shared helpers for UAE analysis tests."""


def data_lines(axis):
    """Return labelled data lines and exclude Matplotlib placeholder lines."""

    return [
        line
        for line in axis.get_lines()
        if line.get_label() and not line.get_label().startswith("_")
    ]


def report_source(content):
    """Store fixture tables in a real DuckDB, including deliberately invalid metadata.

    Excel is only the legacy fixture-authoring format. Production readers receive
    a published reference and exercise normalized report tables without Excel I/O.
    """
    import atexit
    from io import BytesIO
    from pathlib import Path
    import tempfile

    import duckdb
    import pandas as pd
    from htfa.jobs.uae_data.publish_report import _heading
    from htfa.monitoring.uae.database import PublishedUAEData, published_source

    if isinstance(content, PublishedUAEData):
        return content
    if hasattr(content, "getvalue"):
        content = content.getvalue()
    directory = tempfile.TemporaryDirectory(prefix="htfa-uae-test-")
    atexit.register(directory.cleanup)
    database = Path(directory.name) / "fixture.duckdb"
    with pd.ExcelFile(BytesIO(content)) as book:
        tables = {name: book.parse(name, header=None) for name in book.sheet_names}
    # Fixtures need not have a dictionary; source tables still start at index 1.
    dictionary = tables.pop("指标字典", pd.DataFrame())
    with duckdb.connect(str(database)) as con:
        con.execute("CREATE SCHEMA report")
        con.execute("CREATE TABLE report.release AS SELECT 'fixture' AS version, "
                    "1 AS schema_version, TIMESTAMP '2026-10-18' AS published_at")
        con.execute("CREATE TABLE report.sheets (sheet_index INTEGER, sheet_name VARCHAR, "
                    "heading VARCHAR, column_count INTEGER)")
        con.execute("CREATE TABLE report.periods (sheet_index INTEGER, row_index INTEGER, period TIMESTAMP)")
        con.execute("CREATE TABLE report.observations (sheet_index INTEGER, column_index INTEGER, "
                    "period TIMESTAMP, value DOUBLE)")
        for index, (name, raw) in enumerate([("指标字典", dictionary), *tables.items()]):
            con.execute("INSERT INTO report.sheets VALUES (?,?,?,?)", [
                index, name, _heading(raw if index == 0 else raw.iloc[:6]), raw.shape[1],
            ])
            if index == 0:
                continue
            for row_index, row in enumerate(raw.iloc[6:].itertuples(index=False, name=None)):
                period = pd.Timestamp(row[0]).to_pydatetime()
                con.execute("INSERT INTO report.periods VALUES (?,?,?)", [index, row_index, period])
                values = [(index, column, period, float(value)) for column, value in enumerate(row[1:], 1)
                          if pd.notna(value)]
                if values:
                    con.executemany("INSERT INTO report.observations VALUES (?,?,?,?)", values)
    return published_source(database)
