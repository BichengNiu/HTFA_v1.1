"""Published DuckDB reports: fidelity, atomicity, read-only access and versions."""

from pathlib import Path

import duckdb
from openpyxl import Workbook
import pandas as pd
import pytest

from htfa.data.economic_workbook import EconomicWorkbookReader
from htfa.jobs.uae_data import publish_report
from htfa.monitoring.uae.database import published_source


def _workbook(path: Path, value: float = 12) -> None:
    book = Workbook()
    dictionary = book.active
    dictionary.title = "指标字典"
    dictionary.append(["指标名称", "类型", "行业", "数据来源", "预测变量"])
    dictionary.append(["测试指标", "数量", "测试行业", "测试官方", "否"])
    sheet = book.create_sheet("月度_测试")
    for row in [
        ["历史数据", None],
        ["指标名称", "测试指标"],
        ["频率", "月"],
        ["单位", "点"],
        ["来源", "测试官方"],
        ["更新时间", "2026-09-30"],
        [pd.Timestamp("2026-07-31"), value],
        [pd.Timestamp("2026-08-31"), 0],
        [pd.Timestamp("2026-09-30"), None],
    ]:
        sheet.append(row)
    book.save(path)


def _publish(database, workbook):
    with duckdb.connect(str(database)) as con:
        return publish_report.publish_workbook(con, workbook)


def test_database_reader_matches_excel_without_any_excel_io(tmp_path, monkeypatch):
    workbook, database = tmp_path / "book.xlsx", tmp_path / "data.duckdb"
    _workbook(workbook)
    _publish(database, workbook)
    reader = EconomicWorkbookReader("test", "test")
    expected = reader.read(workbook)
    source = published_source(database)
    workbook.unlink()
    monkeypatch.setattr(
        pd, "ExcelFile", lambda *args, **kwargs: pytest.fail("Excel I/O forbidden")
    )

    actual = reader.read(source)

    for frequency in expected.dataframes:
        pd.testing.assert_frame_equal(
            actual.dataframes[frequency], expected.dataframes[frequency],
            check_dtype=False, check_index_type=False,
        )
    with reader.open_workbook(source) as (tables, _):
        values, metadata = reader.read_target_sheet(
            tables, sheet_name="月度_测试", targets=(("test", "测试指标"),),
            allowed_frequencies={"月"}, expected_unit="点", zero_is_missing=False,
        )
        assert values.loc["2026-08-31", "test"] == 0
        assert metadata["test"].source == "测试官方"
        raw = reader.read_raw_sheet(tables, sheet_name="月度_测试")
        raw.iloc[6, 1] = -999
        assert reader.read_raw_sheet(tables, sheet_name="月度_测试").iloc[6, 1] == 12


def test_new_release_invalidates_cached_tables_and_old_references(tmp_path):
    workbook, database = tmp_path / "book.xlsx", tmp_path / "data.duckdb"
    _workbook(workbook)
    _publish(database, workbook)
    old = published_source(database)
    with old.open() as tables:
        assert tables.parse("月度_测试", header=None).iloc[6, 1] == 12
    _workbook(workbook, value=99)
    _publish(database, workbook)
    new = published_source(database)

    assert new.version != old.version
    with new.open() as tables:
        assert tables.parse("月度_测试", header=None).iloc[6, 1] == 99
    with pytest.raises(ValueError, match="版本已更新"):
        with old.open():
            pass


def test_failed_publication_keeps_previous_release(tmp_path, monkeypatch):
    workbook, database = tmp_path / "book.xlsx", tmp_path / "data.duckdb"
    _workbook(workbook)
    previous = _publish(database, workbook)
    _workbook(workbook, value=99)
    original = publish_report._insert_frame

    def fail_observations(con, table, frame):
        if table == "observations":
            raise RuntimeError("publication interrupted")
        return original(con, table, frame)

    monkeypatch.setattr(publish_report, "_insert_frame", fail_observations)
    with pytest.raises(RuntimeError, match="interrupted"):
        _publish(database, workbook)

    source = published_source(database)
    assert source.version == previous["version"]
    with source.open() as tables:
        assert tables.parse("月度_测试", header=None).iloc[6, 1] == 12


def test_missing_database_and_lfs_pointer_are_rejected_without_creating_files(tmp_path):
    path = tmp_path / "missing.duckdb"
    with pytest.raises(FileNotFoundError):
        published_source(path)
    assert not path.exists()
    path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\n")
    with pytest.raises(ValueError, match="LFS 指针"):
        published_source(path)


def test_uae_sidebar_has_no_file_uploader():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
import streamlit as st
from htfa.app.ui.components.sidebar.renderer import render_complete_sidebar
st.session_state["navigation.main_module"] = "监测分析"
st.session_state["navigation.sub_module"] = "阿联酋"
render_complete_sidebar({"监测分析": {"阿联酋": None}})
''').run(timeout=30)

    assert not app.exception
    assert not app.get("file_uploader")
    assert any("无需上传" in item.value for item in app.caption)
