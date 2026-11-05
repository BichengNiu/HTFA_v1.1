"""Retire explicitly discontinued UAE sources from DB, workbook and publication.

Raw downloads and run history remain local audit evidence. Registry removal and
schema removal prevent routine jobs from bringing these indicators back.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile

from openpyxl import load_workbook

from . import db
from .source_registry import RETIRED_SOURCES


RETIRED_INDICATORS = json.loads(
    Path(__file__).with_name("retired_indicators.json").read_text(encoding="utf-8")
)
RETIRED_TABLES = (
    "dld_lease_monthly", "ded_official_news_candidates", "ded_official_news_scan_state",
)
RETIRED_WEEKLY_COLUMNS = (
    "offplan_sales_28d", "project_launch_index", "offplan_absorption_index",
    "project_commercial_transition_index",
)


def _drop_owned_table(con, name: str) -> None:
    """Drop a discontinued table and its legacy same-name main alias."""
    schema, table = name.split(".", 1) if "." in name else ("main", name)
    schemas = ("main", schema) if schema != "main" else (schema,)
    for owner in schemas:
        row = con.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_catalog=current_database() "
            "AND table_schema=? AND table_name=?", [owner, table],
        ).fetchone()
        if row:
            kind = "VIEW" if row[0] == "VIEW" else "TABLE"
            con.execute(f'DROP {kind} "{owner}"."{table}"')
        con.execute(
            "DELETE FROM meta_column_dictionary WHERE object_name IN (?, ?)",
            [table, f"{owner}.{table}"],
        )


def _main_table_exists(con, table: str) -> bool:
    """Check only the current database, excluding attached backup catalogs."""
    return con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_catalog=current_database() AND table_schema='main' AND table_name=?",
        [table],
    ).fetchone() is not None


def retire_database(con) -> None:
    """Remove the retired source tables and their owned indicator metadata."""
    with db.transaction(con):
        con.execute(
            "CREATE TABLE IF NOT EXISTS meta_retired_indicators "
            "(sheet_name VARCHAR, indicator_name VARCHAR, "
            "PRIMARY KEY(sheet_name, indicator_name))"
        )
        con.executemany(
            "INSERT OR IGNORE INTO meta_retired_indicators VALUES (?, ?)",
            [(sheet, name) for sheet, names in RETIRED_INDICATORS.items() for name in names],
        )
        for table, _sheet in RETIRED_SOURCES.values():
            _drop_owned_table(con, table)
        for table in RETIRED_TABLES:
            _drop_owned_table(con, table)
        for table in ("public_market_daily", "fcsc_gdp_quarterly", "dot_t100_monthly"):
            if _main_table_exists(con, table):
                con.execute(
                    f"DELETE FROM {table} WHERE indicator IN "
                    "(SELECT indicator_name FROM meta_retired_indicators)"
                )
        if _main_table_exists(con, "ded_monthly"):
            con.execute("DELETE FROM ded_monthly WHERE series='official_new_licenses'")
        if _main_table_exists(con, "fcsc_investment_annual"):
            con.execute("DELETE FROM fcsc_investment_annual WHERE dataset='DF_NA_EXPEND_CON'")
        if _main_table_exists(con, "dld_investment_pipeline_weekly"):
            for column in RETIRED_WEEKLY_COLUMNS:
                con.execute(
                    f"ALTER TABLE dld_investment_pipeline_weekly DROP COLUMN IF EXISTS {column}"
                )
                con.execute(
                    "DELETE FROM meta_column_dictionary WHERE "
                    "object_name IN ('dld_investment_pipeline_weekly', "
                    "'main.dld_investment_pipeline_weekly') AND column_name=?", [column],
                )
        con.execute(
            "DELETE FROM meta_indicator_dictionary WHERE indicator_name IN "
            "(SELECT indicator_name FROM meta_retired_indicators)"
        )
        con.execute(
            "DELETE FROM meta_indicator_dictionary WHERE source IN (?, ?, ?) "
            "OR indicator_name LIKE ? OR indicator_name LIKE ?",
            ["MEsteel", "TDRA Open Data", "SCAD", "阿联酋:钢材进口报价:%", "阿联酋:TDRA%"],
        )


def retire_workbook(workbook_path: Path) -> list[str]:
    """Atomically remove retired sheets; dictionary synchronization is DB-driven."""
    from .uae_metadata import sync_workbook_dictionary

    path = Path(workbook_path).resolve()
    if path.with_name(f"~${path.name}").exists():
        raise PermissionError("请先关闭 Excel 工作簿")
    book = load_workbook(path, keep_links=True)
    temporary = None
    try:
        removed = [sheet for _table, sheet in RETIRED_SOURCES.values()
                   if sheet in book.sheetnames]
        for sheet in removed:
            book.remove(book[sheet])
        # The retirement decision is first recorded in DuckDB by retire_database.
        # Column names are resolved again at merge time, never stale column indexes.
        with db.connect(read_only=True) as con:
            decisions = con.execute(
                "SELECT sheet_name,indicator_name FROM meta_retired_indicators"
            ).fetchall()
        by_sheet = {}
        for sheet, name in decisions:
            by_sheet.setdefault(sheet, set()).add(name)
        for title, names in by_sheet.items():
            if title not in book.sheetnames:
                continue
            sheet = book[title]
            columns = [col for col in range(2, sheet.max_column + 1)
                       if sheet.cell(2, col).value in names]
            for col in reversed(columns):
                sheet.delete_cols(col)
            if columns:
                removed.append(f"{title}:停用{len(columns)}列")
                if sheet.max_column == 1:
                    book.remove(sheet)
        # Earlier Wind imports also contain copies of the retired hotel series.
        # Match both provider and hotel definition to preserve unrelated data.
        for sheet in book.worksheets:
            if sheet.title == "指标字典":
                continue
            columns = [
                col for col in range(2, sheet.max_column + 1)
                if sheet.cell(5, col).value in {"SCAD", "阿布扎比统计局"}
                and "酒店" in str(sheet.cell(2, col).value or "")
            ]
            for col in reversed(columns):
                sheet.delete_cols(col)
            if columns:
                removed.append(f"{sheet.title}:SCAD酒店{len(columns)}列")
        if not removed:
            return []
        fd, name = tempfile.mkstemp(
            prefix=".retire-sources-", suffix=".tmp.xlsx", dir=path.parent,
        )
        os.close(fd)
        temporary = Path(name)
        book.save(temporary)
        book.close()
        sync_workbook_dictionary(temporary)
        backups = path.parent / "backups"
        backups.mkdir(exist_ok=True)
        shutil.copy2(path, backups / f"retired_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx")
        os.replace(temporary, path)
        return removed
    finally:
        book.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
