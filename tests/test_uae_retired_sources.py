"""Retired data cannot return through normal schema, update or merge entrypoints."""

from datetime import date

from openpyxl import Workbook, load_workbook
import pytest

from htfa.jobs.uae_data import db
from htfa.jobs.uae_data.retired_sources import retire_database, retire_workbook
from htfa.jobs.uae_data.source_registry import resolve_source_names


def test_retired_sources_are_not_registered_or_created():
    assert not {"steel", "tdra"} & set(resolve_source_names("all"))
    for name in ("steel", "tdra"):
        with pytest.raises(ValueError, match="Unknown source"):
            resolve_source_names(name)
    with db.connect(":memory:") as con:
        db.init_schema(con)
        assert not db.table_exists(con, "mesteel_monthly")
        assert not db.table_exists(con, "tdra_telecom_monthly")


def test_retirement_preserves_replacement_and_unrelated_data(tmp_path, monkeypatch):
    database = tmp_path / "uae.duckdb"
    with db.connect(database) as con:
        db.init_schema(con)
        for table in ("mesteel_monthly", "tdra_telecom_monthly", "emsteel_monthly"):
            con.execute(f"CREATE TABLE {table}(value INTEGER)")
            con.execute(f"INSERT INTO {table} VALUES(123)")
        db.upsert_dictionary_rows(con, [
            dict(indicator_name="旧钢材", source="MEsteel"),
            dict(indicator_name="旧电信", source="TDRA Open Data"),
            dict(indicator_name="新钢材", source="Quanto"),
        ])
        retire_database(con)
        retire_database(con)
        assert con.execute("SELECT value FROM emsteel_monthly").fetchone() == (123,)
        assert con.execute("SELECT indicator_name FROM meta_indicator_dictionary").fetchall() == [("新钢材",)]
    connect = db.connect
    monkeypatch.setattr(db, "connect", lambda **kw: connect(database, **kw))
    path = tmp_path / "data.xlsx"
    book = Workbook()
    book.active.title = "指标字典"
    book.active.append(["指标名称", "类型", "行业", "频率", "开始日期", "最新日期", "缺失期数", "数据来源", "预测变量"])
    book.active.append(["旧钢材"])
    book.active.append(["旧电信"])
    for name in ("月度_MEsteel", "月度_TDRA", "月度_EMSTEEL", "用户数据"):
        book.create_sheet(name)
    book["月度_EMSTEEL"]["B2"] = "新钢材"
    book["月度_EMSTEEL"]["A2"] = "指标名称"
    book["月度_EMSTEEL"]["B3"] = "月"
    book["月度_EMSTEEL"]["B4"] = "迪拉姆/吨"
    book["月度_EMSTEEL"]["B5"] = "Quanto"
    book["月度_EMSTEEL"]["A7"] = date(2026, 10, 31)
    book["月度_EMSTEEL"]["B7"] = 123
    book["用户数据"]["A1"] = "保留"
    book.save(path)
    book.close()
    assert retire_workbook(path) == ["月度_MEsteel", "月度_TDRA"]
    assert retire_workbook(path) == []
    book = load_workbook(path)
    assert book.sheetnames == ["指标字典", "月度_EMSTEEL", "用户数据"]
    assert book["用户数据"]["A1"].value == "保留"
    assert [row[0] for row in book["指标字典"].iter_rows(
        min_row=2, max_col=1, values_only=True,
    ) if row[0] is not None] == ["新钢材"]
    book.close()
    assert not list(tmp_path.glob(".retire-sources-*"))
