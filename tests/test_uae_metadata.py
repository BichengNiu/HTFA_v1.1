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


def test_legacy_workbook_indicators_have_source_metadata() -> None:
    names = {
        "阿联酋DFM综合股票指数",
        "全球:现货均价:原油(阿联酋穆尔班)",
        "期货结算价(连续):布伦特原油",
        "全球:现货价:原油(英国布伦特Dtd)",
        "全球:现货价:原油(阿联酋迪拜)",
        "阿联酋:现货价(CIF,低端价):石脑油",
        "阿联酋:现货价(CIF,低端价):汽油(优质无铅)",
        "阿联酋:现货价(CIF,低端价):柴油(Gasoil.1)",
        "阿联酋:现货价(CIF,低端价):煤油(航空)",
        "中国:广州市场:市场价(主流价):线型低密度聚乙烯(FB2230膜料):阿联酋博禄化工",
        "阿联酋:现货价(CIF,低端价):柴油(10ppm)",
        "印度:出口数量:咖啡:阿联酋:累计值",
        "阿联酋:银行间同业拆借利率(EIBOR):1年",
        "美元兑阿联酋迪拉姆",
        "人民币兑阿联酋迪拉姆",
        "阿联酋:银行间同业拆借利率(EIBOR):隔夜",
        "阿联酋:港口到港总次数:当月值",
        "阿联酋:港口集装箱到港次数:当月值",
        "阿联酋:港口油轮到港次数:当月值",
        "阿联酋:港口进口总量:当月值",
        "阿联酋:港口集装箱进口量:当月值",
        "阿联酋:港口油轮进口量:当月值",
        "阿联酋:港口出口总量:当月值",
        "阿联酋:港口集装箱出口量:当月值",
        "阿联酋:港口油轮出口量:当月值",
        "霍尔木兹:过境总次数:当月值",
        "霍尔木兹:载货容量:当月值",
        "霍尔木兹:油轮过境次数:当月值",
        "霍尔木兹:油轮载货容量:当月值",
    }
    definitions = {
        row["indicator_name"]: row for row in uae_metadata.INDICATOR_DEFINITIONS
    }

    assert names <= definitions.keys()
    assert all(definitions[name]["source"] for name in names)


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
