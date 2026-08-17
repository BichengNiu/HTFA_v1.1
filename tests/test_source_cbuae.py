"""Tests for ``data/source_cbuae.py``（DuckDB 入库版）。"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

import db  # noqa: E402
import source_cbuae as source  # noqa: E402


def _bulletin_workbook(path: Path) -> None:
    """构造一份模拟真实统计公报的迷你工作簿（2020-01、2020-02 两期）。"""

    workbook = Workbook()
    credit = workbook.active
    credit.title = "20 Dom Crd"
    credit.append(
        ["Table 20: Domestic Credit (All Banks)", "January 2020", "February 2020"]
    )
    credit.append([None, None, None])
    credit.append(["Government", 100, 101])
    credit.append(["Public Sector ( GREs )", 50, 51])

    deposit = workbook.create_sheet("25 Dep")
    deposit.append(
        [
            "Deposits distributed Residents / Non Residents ( All Banks )",
            "January 2020",
            "February 2020",
        ]
    )
    deposit.append([None, None, None])
    deposit.append(["Government", 200, 201])
    deposit.append(["GREs", 100, 101])

    workbook.save(path)
    workbook.close()


def _wind_workbook(path: Path) -> None:
    """构造月度_Wind sheet：2019-12 可回填、2020-01 已存在主序列不应覆盖。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_Wind"
    sheet.append(["Wind", None, None, None, None])
    sheet.append(["指标名称", *source.WIND_FALLBACK_INDICATORS])
    sheet.append(["频率", "月", "月", "月", "月"])
    sheet.append(["单位", *("十亿阿联酋迪拉姆",) * 4])
    sheet.append(["来源", *("Wind",) * 4])
    sheet.append(["更新时间", *("2026-08-11",) * 4])
    sheet.append([date(2019, 12, 31), 1.0, 2.0, 3.0, 4.0])
    sheet.append([date(2020, 1, 31), 999.0, 999.0, 999.0, 999.0])
    workbook.save(path)
    workbook.close()


def test_extract_workbook_returns_both_periods(tmp_path) -> None:
    bulletin = tmp_path / "2020-03.xlsx"
    _bulletin_workbook(bulletin)

    observations = source.extract_workbook(bulletin)

    assert [item.period for item in observations] == ["2020-01", "2020-02"]
    assert observations[0].values == (
        Decimal("200.000"),
        Decimal("100.000"),
        Decimal("100.000"),
        Decimal("50.000"),
    )
    assert observations[0].source_period == "2020-03"
    assert observations[0].source_file == "2020-03.xlsx"


def test_update_roundtrip_long_table_with_wind_fallback(
    tmp_path, monkeypatch
) -> None:
    """解析 -> 入库往返：长表 3 期 × 4 指标；缺期由 Wind 回填且不覆盖主序列。"""

    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    monkeypatch.setattr(source, "WIND_PATH", tmp_path / "wind.xlsx")
    _bulletin_workbook(tmp_path / "2020-03.xlsx")
    _wind_workbook(tmp_path / "wind.xlsx")

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = source.update(con, skip_download=True)

    assert outcome["status"] == "ok"
    assert outcome["rows"] == 12  # 2019-12, 2020-01, 2020-02 × 4 指标

    count = con.execute("SELECT COUNT(*) FROM cbuae_monthly").fetchone()[0]
    periods = con.execute(
        "SELECT DISTINCT period FROM cbuae_monthly ORDER BY period"
    ).fetchall()
    assert periods == [(date(2019, 12, 31),), (date(2020, 1, 31),), (date(2020, 2, 29),)]

    # 2019-12 由 Wind 回填：十亿 → 百万
    wind_value = con.execute(
        "SELECT value FROM cbuae_monthly "
        "WHERE period = ? AND indicator = ?",
        [date(2019, 12, 31), "阿联酋政府存款"],
    ).fetchone()[0]
    assert wind_value == Decimal("1000.000")
    wind_source = con.execute(
        "SELECT source_file FROM cbuae_monthly WHERE period = ? AND indicator = ?",
        [date(2019, 12, 31), "阿联酋政府存款"],
    ).fetchone()[0]
    assert wind_source == "wind.xlsx"

    # 2020-01 必须来自公报（Wind 同期待填值不覆盖主序列）
    primary_value = con.execute(
        "SELECT value FROM cbuae_monthly "
        "WHERE period = ? AND indicator = ?",
        [date(2020, 1, 31), "阿联酋政府存款"],
    ).fetchone()[0]
    assert primary_value == Decimal("200.000")
    primary_source = con.execute(
        "SELECT source_file FROM cbuae_monthly WHERE period = ? AND indicator = ?",
        [date(2020, 1, 31), "阿联酋政府信贷"],
    ).fetchone()[0]
    assert primary_source == "2020-03.xlsx"

    con.close()


def test_update_writes_four_dictionary_rows(tmp_path, monkeypatch) -> None:
    """指标字典应写入 CBUAE 的 4 行（名称/类型/行业/频率/单位/来源）。"""

    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    monkeypatch.setattr(source, "WIND_PATH", tmp_path / "wind.xlsx")
    _bulletin_workbook(tmp_path / "2020-03.xlsx")
    _wind_workbook(tmp_path / "wind.xlsx")

    con = db.connect(":memory:")
    db.init_schema(con)
    source.update(con, skip_download=True)

    dictionary = con.execute(
        "SELECT indicator_name, type, industry, frequency, unit, source "
        "FROM meta_indicator_dictionary ORDER BY indicator_name"
    ).fetchall()
    con.close()
    assert len(dictionary) == 4
    assert ("阿联酋政府存款", "存款", "金融", "月", "百万迪拉姆", "CBUAE") in dictionary
    assert ("阿联酋政府控股企业存款", "存款", "金融", "月", "百万迪拉姆", "CBUAE") in dictionary
    assert ("阿联酋政府信贷", "信贷", "金融", "月", "百万迪拉姆", "CBUAE") in dictionary
    assert ("阿联酋政府控股企业信贷", "信贷", "金融", "月", "百万迪拉姆", "CBUAE") in dictionary


def test_select_latest_vintages_prefers_newer_bulletin(tmp_path, monkeypatch) -> None:
    """同一期间出现两个 vintage 时选择较新公报，并报告修订期数。"""

    old_bulletin = tmp_path / "2020-02.xlsx"
    _bulletin_workbook(old_bulletin)
    # 新公报覆盖同一期间且数值不同（政府存款 200 -> 250）
    workbook = Workbook()
    credit = workbook.active
    credit.title = "20 Dom Crd"
    credit.append(["Table 20: Domestic Credit (All Banks)", "January 2020"])
    credit.append([None, None])
    credit.append(["Government", 100])
    credit.append(["Public Sector ( GREs )", 50])
    deposit = workbook.create_sheet("25 Dep")
    deposit.append(
        ["Deposits distributed Residents / Non Residents ( All Banks )", "January 2020"]
    )
    deposit.append([None, None])
    deposit.append(["Government", 250])
    deposit.append(["GREs", 100])
    workbook.save(tmp_path / "2020-03.xlsx")
    workbook.close()

    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    monkeypatch.setattr(source, "WIND_PATH", tmp_path / "wind.xlsx")
    _wind_workbook(tmp_path / "wind.xlsx")

    con = db.connect(":memory:")
    db.init_schema(con)
    source.update(con, skip_download=True)

    value = con.execute(
        "SELECT value, source_period FROM cbuae_monthly "
        "WHERE period = ? AND indicator = ?",
        [date(2020, 1, 31), "阿联酋政府存款"],
    ).fetchone()
    con.close()
    assert value == (Decimal("250.000"), "2020-03")