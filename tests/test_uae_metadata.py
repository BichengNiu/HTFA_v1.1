"""Regression tests for the DuckDB and workbook metadata completion path."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "data" / "UAE" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
import uae_metadata  # noqa: E402


def test_complete_metadata_registers_extended_indicators_and_columns() -> None:
    con = db.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE portwatch_uae_daily (
                date DATE, portcalls BIGINT
            )
            """
        )
        con.execute("CREATE SCHEMA dld")
        con.execute(
            """
            CREATE TABLE dld.transactions (
                transaction_id VARCHAR
            )
            """
        )
        result = uae_metadata.complete_metadata(con)
        assert result["indicator_rows"] == len(uae_metadata.INDICATOR_DEFINITIONS)
        assert result["column_rows"] > 0

        names = {
            row[0]
            for row in con.execute(
                "SELECT indicator_name FROM meta_indicator_dictionary"
            ).fetchall()
        }
        assert "菲律宾_DMW部署_总计" in names
        assert "迪拜:当月新发执照数(执照号筛重)" in names
        assert "阿联酋:Google搜索热度(work in uae)" in names

        detail_columns = con.execute(
            """
            SELECT object_name, column_name
            FROM meta_column_dictionary
            WHERE object_name IN (
                'foreign_labour_monthly', 'ded_monthly',
                'portwatch_uae_daily', 'dld.transactions'
            )
            """
        ).fetchall()
        assert ("foreign_labour_monthly", "quality_flag") in detail_columns
        assert ("ded_monthly", "series") in detail_columns
        assert ("portwatch_uae_daily", "portcalls") in detail_columns
        assert ("dld.transactions", "transaction_id") in detail_columns
    finally:
        con.close()


def test_complete_metadata_is_idempotent() -> None:
    con = db.connect(":memory:")
    try:
        uae_metadata.complete_metadata(con)
        first = con.execute(
            "SELECT count(*) FROM meta_indicator_dictionary"
        ).fetchone()[0]
        uae_metadata.complete_metadata(con)
        second = con.execute(
            "SELECT count(*) FROM meta_indicator_dictionary"
        ).fetchone()[0]
        assert second == first
    finally:
        con.close()


def test_sync_workbook_dictionary_removes_unbacked_rows(tmp_path, monkeypatch) -> None:
    from openpyxl import Workbook, load_workbook

    workbook_path = tmp_path / "workbook.xlsx"
    workbook = Workbook()
    dictionary = workbook.active
    dictionary.title = "指标字典"
    dictionary.append(["指标名称", "类型", "行业", "数据来源", "预测变量"])
    dictionary.append(["指标A", "旧类型", "旧行业", "旧来源", None])
    dictionary.append(["孤立指标", "类型", "行业", "来源", None])
    data = workbook.create_sheet("月度_测试")
    data.append(["测试数据", None])
    data.append(["指标名称", "指标A"])
    data.append(["频率", "月"])
    data.append(["单位", "点"])
    data.append(["来源", "测试源"])
    data.append(["更新时间", "2026-08-20"])
    data.append(["2026-07-31", 1])
    workbook.save(workbook_path)

    class _Result:
        def fetchall(self):
            return [("指标A", "新类型", "新行业", "新来源")]

    class _Connection:
        def execute(self, _query):
            return _Result()

        def close(self):
            pass

    monkeypatch.setattr(uae_metadata.db, "connect", lambda read_only=True: _Connection())
    result = uae_metadata.sync_workbook_dictionary(workbook_path)

    assert result["removed"] == 1
    loaded = load_workbook(workbook_path, read_only=True, data_only=True)
    rows = list(loaded.worksheets[0].iter_rows(min_row=2, values_only=True))
    assert [row[0] for row in rows if row[0]] == ["指标A"]
    assert rows[0][1:4] == ("新类型", "新行业", "新来源")
