"""Retired data cannot return through normal schema, update or merge entrypoints."""

from datetime import date
from importlib.util import find_spec

from openpyxl import Workbook, load_workbook
import pytest

from htfa.monitoring.uae.jobs import db
from htfa.monitoring.uae.jobs.retired_sources import retire_database, retire_workbook
from htfa.monitoring.uae.jobs.source_registry import resolve_source_names


def test_retired_sources_are_not_registered_or_created():
    retired = ("steel", "tdra", "scad", "uaewps", "emirates_post", "eurostat_air")
    assert not set(retired) & set(resolve_source_names("all"))
    for name in retired:
        assert find_spec(f"htfa.monitoring.uae.jobs.source_{name}") is None
        with pytest.raises(ValueError, match="Unknown source"):
            resolve_source_names(name)
    with db.connect(":memory:") as con:
        db.init_schema(con)
        assert not db.table_exists(con, "mesteel_monthly")
        assert not db.table_exists(con, "tdra_telecom_monthly")
        assert not db.table_exists(con, "scad_monthly")
        for name in ("uaewps_monthly", "dld_lease_monthly",
                     "detail.emirates_post_monthly", "detail.eurostat_air_monthly"):
            assert not db.table_exists(con, name)


def test_retirement_preserves_replacement_and_unrelated_data(tmp_path, monkeypatch):
    database = tmp_path / "uae.duckdb"
    with db.connect(database) as con:
        db.init_schema(con)
        for table in ("mesteel_monthly", "tdra_telecom_monthly", "scad_monthly", "emsteel_monthly"):
            con.execute(f"CREATE TABLE {table}(value INTEGER)")
            con.execute(f"INSERT INTO {table} VALUES(123)")
        db.upsert_dictionary_rows(con, [
            dict(indicator_name="旧钢材", source="MEsteel"),
            dict(indicator_name="旧电信", source="TDRA Open Data"),
            dict(indicator_name="旧酒店", source="SCAD"),
            dict(indicator_name="新钢材", source="Quanto"),
        ])
        retire_database(con)
        retire_database(con)
        assert con.execute("SELECT value FROM emsteel_monthly").fetchone() == (123,)
        assert con.execute("SELECT indicator_name FROM meta_indicator_dictionary").fetchall() == [("新钢材",)]
    connect = db.connect
    monkeypatch.setattr(db, "connect", lambda _database=None, **kw: connect(database, **kw))
    path = tmp_path / "data.xlsx"
    book = Workbook()
    book.active.title = "指标字典"
    book.active.append(["指标名称", "类型", "行业", "频率", "开始日期", "最新日期", "缺失期数", "数据来源", "预测变量"])
    book.active.append(["旧钢材"])
    book.active.append(["旧电信"])
    for name in ("月度_MEsteel", "月度_TDRA", "月度_SCAD", "月度_EMSTEEL", "用户数据"):
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
    assert retire_workbook(path) == ["月度_MEsteel", "月度_TDRA", "月度_SCAD"]
    assert retire_workbook(path) == []
    book = load_workbook(path)
    assert book.sheetnames == ["指标字典", "月度_EMSTEEL", "用户数据"]
    assert book["用户数据"]["A1"].value == "保留"
    assert [row[0] for row in book["指标字典"].iter_rows(
        min_row=2, max_col=1, values_only=True,
    ) if row[0] is not None] == ["新钢材"]
    book.close()
    assert not list(tmp_path.glob(".retire-sources-*"))


def test_retirement_removes_legacy_hotel_columns_without_removing_other_scad_data(tmp_path, monkeypatch):
    import htfa.monitoring.uae.jobs.uae_metadata as metadata

    monkeypatch.setattr(metadata, "sync_workbook_dictionary", lambda path: {})
    database = tmp_path / "uae.duckdb"
    with db.connect(database) as con:
        db.init_schema(con)
        retire_database(con)
    connect = db.connect
    monkeypatch.setattr(db, "connect", lambda _database=None, **kw: connect(database, **kw))
    path = tmp_path / "legacy.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "月度_Wind"
    for col, title, source in [(2, "阿布扎比:客房入住率:酒店", "阿布扎比统计局"),
                               (3, "阿布扎比:其他指标", "阿布扎比统计局"),
                               (4, "其他地区:酒店", "其他来源")]:
        sheet.cell(2, col, title)
        sheet.cell(5, col, source)
        sheet.cell(7, col, col * 10)
    book.save(path)
    book.close()
    assert retire_workbook(path) == ["月度_Wind:SCAD酒店1列"]
    assert retire_workbook(path) == []
    book = load_workbook(path)
    assert book.active.cell(2, 2).value == "阿布扎比:其他指标"
    assert book.active.cell(7, 2).value == 30
    assert book.active.cell(2, 3).value == "其他地区:酒店"
    book.close()
