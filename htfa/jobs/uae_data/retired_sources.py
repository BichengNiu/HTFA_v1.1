"""Retire explicitly discontinued UAE sources from DB, workbook and publication.

Raw downloads and run history remain local audit evidence. Registry removal and
schema removal prevent routine jobs from bringing these indicators back.
"""

from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile

from openpyxl import load_workbook

from . import db
from .source_registry import RETIRED_SOURCES


def retire_database(con) -> None:
    """Remove the retired source tables and their owned indicator metadata."""
    with db.transaction(con):
        for table, _sheet in RETIRED_SOURCES.values():
            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(
                "DELETE FROM meta_column_dictionary WHERE object_name IN (?, ?)",
                [table, f"main.{table}"],
            )
        con.execute(
            "DELETE FROM meta_indicator_dictionary WHERE source IN (?, ?) "
            "OR indicator_name LIKE ? OR indicator_name LIKE ?",
            ["MEsteel", "TDRA Open Data", "阿联酋:钢材进口报价:%", "阿联酋:TDRA%"],
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
        if not removed:
            return []
        for sheet in removed:
            book.remove(book[sheet])
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
