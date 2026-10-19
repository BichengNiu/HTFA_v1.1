"""Publish the validated local workbook as normalized DuckDB report tables.

The workbook contains historical indicators not yet covered by source jobs.
This publication preserves those histories alongside the source-backed sheets.
Cloud readers consume these tables without opening or generating an Excel file.
"""

from datetime import date, datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

import pandas as pd

from htfa.data.economic_workbook import EconomicWorkbookReader
from htfa.monitoring.uae.database import REPORT_SCHEMA_VERSION

from . import db


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported report metadata: {type(value).__name__}")


def _heading(raw: pd.DataFrame) -> str:
    rows = [
        [None if pd.isna(value) else value for value in row]
        for row in raw.itertuples(index=False, name=None)
    ]
    return json.dumps(rows, default=_json_default, ensure_ascii=False, allow_nan=False)


def _insert_frame(con, table: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    con.register("_report_input", frame)
    try:
        con.execute(f"INSERT INTO report.{table} SELECT * FROM _report_input")
    finally:
        con.unregister("_report_input")


def publish_workbook(con, workbook_path: Path) -> dict:
    """Atomically publish all report series after workbook protocol validation.

    ``con`` is the writable pipeline connection. ``workbook_path`` is the
    successfully merged local workbook; cloud processes never invoke this job.
    A failed parse or insert rolls back the entire publication.
    """
    path = Path(workbook_path)
    content = path.read_bytes()
    validated = BytesIO(content)
    validated.name = path.name
    # Validate the existing economic protocol, including duplicate names,
    # dictionary membership, units, frequencies and numeric data.
    EconomicWorkbookReader("uae_publication", "uae_publication").read(validated)
    version = hashlib.sha256(content).hexdigest()
    with pd.ExcelFile(BytesIO(content)) as workbook:
        tables = [(name, workbook.parse(name, header=None)) for name in workbook.sheet_names]
    with db.transaction(con):
        con.execute("CREATE SCHEMA IF NOT EXISTS report")
        con.execute("CREATE TABLE IF NOT EXISTS report.release ("
                    "version VARCHAR, schema_version INTEGER, published_at TIMESTAMP)")
        con.execute("CREATE TABLE IF NOT EXISTS report.sheets ("
                    "sheet_index INTEGER PRIMARY KEY, sheet_name VARCHAR UNIQUE, "
                    "heading VARCHAR, column_count INTEGER)")
        con.execute("CREATE TABLE IF NOT EXISTS report.periods ("
                    "sheet_index INTEGER, row_index INTEGER, period TIMESTAMP, "
                    "PRIMARY KEY(sheet_index, period))")
        con.execute("CREATE TABLE IF NOT EXISTS report.observations ("
                    "sheet_index INTEGER, column_index INTEGER, period TIMESTAMP, "
                    "value DOUBLE, "
                    "PRIMARY KEY(sheet_index, column_index, period))")
        for table in ("release", "sheets", "periods", "observations"):
            con.execute(f"DELETE FROM report.{table}")
        count = 0
        for index, (name, raw) in enumerate(tables):
            con.execute("INSERT INTO report.sheets VALUES (?,?,?,?)", [
                index, name, _heading(raw if index == 0 else raw.iloc[:6]),
                raw.shape[1],
            ])
            if index == 0 or raw.dropna(how="all").empty:
                continue
            block = raw.iloc[6:].dropna(how="all").copy()
            periods = pd.to_datetime(block.iloc[:, 0], errors="raise")
            if periods.isna().any() or periods.duplicated().any():
                raise ValueError(f"报告表 {name} 存在空日期或重复日期")
            _insert_frame(con, "periods", pd.DataFrame({
                "sheet_index": index, "row_index": range(len(block)),
                "period": periods.to_numpy(),
            }))
            block.iloc[:, 0] = periods.to_numpy()
            long = block.melt(id_vars=[0], var_name="column_index", value_name="raw")
            long = long.dropna(subset=["raw"])
            numeric = pd.to_numeric(long["raw"], errors="raise")
            if numeric.isin([float("inf"), float("-inf")]).any():
                raise ValueError(f"报告表 {name} 存在非有限数值")
            data = pd.DataFrame({
                "sheet_index": index, "column_index": long["column_index"],
                "period": long[0], "value": numeric,
            })
            _insert_frame(con, "observations", data)
            count += len(data)
        con.execute("INSERT INTO report.release VALUES (?,?,?)", [
            version, REPORT_SCHEMA_VERSION, datetime.now(timezone.utc).replace(tzinfo=None),
        ])
    return {"version": version, "sheets": len(tables), "observations": count}
