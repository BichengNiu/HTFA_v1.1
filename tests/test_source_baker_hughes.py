"""Tests for ``data/source_baker_hughes.py``（DuckDB 入库版）。"""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
import source_baker_hughes as source  # noqa: E402


def _source_workbook(path, *, year: int = 2026, month: int = 7) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "WW Monthly"
    sheet.append(["WORLDWIDE Monthly Rig Count Report"])
    sheet.append(
        [
            "Region",
            "Country",
            "DrillFor",
            "Location",
            "Rig Status",
            "Year",
            "Month",
            "Rig Count Value",
        ]
    )
    sheet.append(
        ["Middle East", "UAE - ABU DHABI", "Oil", "Land", "Active Rigs", year, month, 50]
    )
    sheet.append(
        ["Middle East", "UAE - ABU DHABI", "Gas", "Offshore", "Active Rigs", year, month, 10]
    )
    sheet.append(
        ["Middle East", "UAE - DUBAI", "Oil", "Offshore", "Active Rigs", year, month, 2]
    )
    sheet.append(
        ["Middle East", "SAUDI ARABIA", "Oil", "Land", "Operating Rigs", year, month, 90]
    )
    workbook.save(path)
    workbook.close()


def test_extract_uae_monthly_aggregates_emirates_and_ignores_non_oil(
    tmp_path,
) -> None:
    source_file = tmp_path / "report.xlsx"
    _source_workbook(source_file)

    observations = source.extract_uae_monthly(source_file)

    assert observations == [
        source.RigObservation(period="2026-07", oil=Decimal("52"))
    ]


def test_select_latest_workbook_uses_observation_month_not_filename(
    tmp_path,
) -> None:
    older = tmp_path / "z-later-looking-name.xlsx"
    newer = tmp_path / "a-earlier-looking-name.xlsx"
    _source_workbook(older, month=7)
    _source_workbook(newer, month=8)

    selected, observations, errors = source.select_latest_workbook(tmp_path)

    assert selected == newer
    assert observations[-1].period == "2026-08"
    assert errors == []


def test_update_loads_monthly_table_and_dictionary(tmp_path, monkeypatch) -> None:
    """解析 -> 入库往返：月份落在月末、钻机数为整数、字典一行。"""

    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    _source_workbook(tmp_path / "workbook.xlsx")

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = source.update(con, skip_download=True)
    con.close()

    assert outcome["status"] == "ok"
    assert outcome["rows"] == 1


def test_update_roundtrip_values(tmp_path, monkeypatch) -> None:
    """内存库往返：period 为月末 DATE、oil_rigs 聚合为 52。"""

    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    _source_workbook(tmp_path / "workbook.xlsx")

    con = db.connect(":memory:")
    db.init_schema(con)
    source.update(con, skip_download=True)

    period, oil_rigs = con.execute(
        "SELECT period, oil_rigs FROM baker_hughes_monthly"
    ).fetchone()
    rows = con.execute("SELECT COUNT(*) FROM baker_hughes_monthly").fetchone()[0]
    con.close()

    assert rows == 1
    assert period == date(2026, 7, 31)
    assert oil_rigs == 52

    con = db.connect(":memory:")
    db.init_schema(con)
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    source.update(con, skip_download=True)
    dictionary_row = con.execute(
        "SELECT indicator_name, frequency, unit, source, type, industry "
        "FROM meta_indicator_dictionary WHERE indicator_name = ?",
        ["阿联酋石油活跃钻机数"],
    ).fetchone()
    con.close()
    assert dictionary_row == (
        "阿联酋石油活跃钻机数",
        "月",
        "台",
        "Baker Hughes",
        "数量",
        "能源",
    )


def test_target_is_current_compares_managed_series(tmp_path) -> None:
    target = tmp_path / "阿联酋.xlsx"
    observation = source.RigObservation(period="2026-07", oil=Decimal("52"))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_贝克休斯"
    sheet.append(["Baker Hughes", *([None] * len(source.INDICATORS))])
    sheet.append(["指标名称", *(name for name, _ in source.INDICATORS)])
    sheet.append(["频率", *(["月"] * len(source.INDICATORS))])
    sheet.append(["单位", *(["台"] * len(source.INDICATORS))])
    sheet.append(["来源", *(["Baker Hughes"] * len(source.INDICATORS))])
    sheet.append(["更新时间", *([datetime(2026, 8, 12)] * len(source.INDICATORS))])
    sheet.append([datetime(2026, 7, 31), *observation.values])
    workbook.save(target)
    workbook.close()

    assert source.target_is_current(target, [observation])


def test_target_is_current_false_on_stale_values(tmp_path) -> None:
    """数值不一致时幂等检查应返回 False（触发重写）。"""

    target = tmp_path / "阿联酋.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_贝克休斯"
    sheet.append(["Baker Hughes", None])
    sheet.append(["指标名称", "阿联酋石油活跃钻机数"])
    sheet.append(["频率", "月"])
    sheet.append(["单位", "台"])
    sheet.append(["来源", "Baker Hughes"])
    sheet.append(["更新时间", datetime(2026, 8, 12)])
    sheet.append([datetime(2026, 7, 31), 59])
    workbook.save(target)
    workbook.close()

    assert not source.target_is_current(
        target, [source.RigObservation(period="2026-07", oil=Decimal("52"))]
    )
