"""Read the published UAE report tables directly from a DuckDB snapshot."""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

import duckdb
import pandas as pd

from htfa.data.economic_workbook.tables import EconomicTableSource, TableWorkbook


DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / "data/UAE/uae.duckdb"
REPORT_SCHEMA_VERSION = 1


def _release(con):
    rows = con.execute(
        "SELECT version, schema_version, published_at FROM report.release"
    ).fetchall()
    if len(rows) != 1 or rows[0][1] != REPORT_SCHEMA_VERSION:
        raise ValueError("UAE 数据库尚未发布可用报告，请运行统一合并脚本")
    return rows[0]


def _check_version(con, version: str) -> None:
    if _release(con)[0] != version:
        raise ValueError("UAE 数据版本已更新，请重新运行页面")


@lru_cache(maxsize=64)
def _read_sheet(path: str, version: str, sheet_name: str) -> pd.DataFrame:
    """Cache immutable report tables by their published content version."""
    with duckdb.connect(path, read_only=True) as con:
        con.begin()
        _check_version(con, version)
        record = con.execute(
            "SELECT sheet_index, heading, column_count FROM report.sheets "
            "WHERE sheet_name = ?", [sheet_name],
        ).fetchone()
        if record is None:
            raise ValueError(f"数据库缺少报告表：{sheet_name}")
        index, heading, width = record
        rows = json.loads(heading)
        if index == 0:
            return pd.DataFrame(rows)
        periods = con.execute(
            "SELECT row_index, period FROM report.periods "
            "WHERE sheet_index = ? ORDER BY row_index", [index],
        ).fetchall()
        offsets = {}
        for row_index, period in periods:
            offsets[period] = len(rows)
            rows.append([period, *([None] * (width - 1))])
        values = con.execute(
            "SELECT column_index, period, value FROM report.observations "
            "WHERE sheet_index = ?", [index],
        ).fetchall()
        for column, period, value in values:
            rows[offsets[period]][column] = value
        return pd.DataFrame(rows, columns=range(width))


@dataclass(frozen=True)
class PublishedUAEData(EconomicTableSource):
    """A small, hashable reference to one validated database publication."""

    path: str
    version: str
    published_at: str
    name: str = "uae.duckdb"

    @contextmanager
    def open(self):
        """Verify the release and expose cached tables without Excel I/O."""
        with duckdb.connect(self.path, read_only=True) as con:
            con.begin()
            _check_version(con, self.version)
            names = [row[0] for row in con.execute(
                "SELECT sheet_name FROM report.sheets ORDER BY sheet_index"
            ).fetchall()]
        yield TableWorkbook(
            names, lambda name: _read_sheet(self.path, self.version, name)
        )


def published_source(database: Path | None = None) -> PublishedUAEData:
    """Get the current release, rejecting missing files and LFS pointers."""
    path = Path(database or DEFAULT_DATABASE).resolve()
    if not path.is_file():
        raise FileNotFoundError("未找到 UAE 数据库，请确认部署已拉取 Git LFS 数据")
    with path.open("rb") as stream:
        if stream.read(64).startswith(b"version https://git-lfs.github.com/spec/"):
            raise ValueError("UAE 数据库仍是 Git LFS 指针，请检查云端 LFS 下载")
    try:
        with duckdb.connect(str(path), read_only=True) as con:
            version, _, published_at = _release(con)
    except duckdb.Error as exc:
        raise ValueError("UAE 数据库没有有效报告，请先运行统一合并脚本并推送") from exc
    return PublishedUAEData(
        str(path), version, published_at.strftime("%Y-%m-%d %H:%M:%S")
    )
