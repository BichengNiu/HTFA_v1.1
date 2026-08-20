"""Tests for ``data/source_pmi.py``（DuckDB 入库版）。"""

import calendar
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
import source_pmi as source  # noqa: E402


def _make_payload(periods, values=None) -> list:
    """构造 Trading Economics 风格的图表 payload。"""

    data = []
    for index, period in enumerate(periods):
        value = values[index] if values else 50.0 + (index % 5)
        data.append([value, 1111111111, None, f"{period}-01"])
    return [
        {
            "series": [
                {
                    "serie": {
                        "data": data,
                        "source": "S&P Global",
                        "frequency": "monthly",
                        "country": "United Arab Emirates",
                        "unit": "points",
                    }
                }
            ]
        }
    ]


def _recent_periods(count: int = 30) -> list[str]:
    """生成截至上个月的连续月份（保证时效性检查通过）。"""

    end = (date.today().replace(day=1) - timedelta(days=1))
    year, month = end.year, end.month
    periods: list[str] = []
    for _ in range(count):
        periods.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(periods))


def _write_metadata(path: Path, periods: list[str]) -> dict:
    meta = {
        "observation_count": len(periods),
        "source_last_update": periods[-1].replace("-", "") + "010000",
        "coverage_note": "limited sample",
    }
    path.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def test_load_observations_parses_and_sorts(tmp_path) -> None:
    chart = tmp_path / "chart.json"
    chart.write_text(
        json.dumps(_make_payload(["2026-03", "2026-01", "2026-02"])),
        encoding="utf-8",
    )

    observations = source.load_observations(chart)

    assert [item.period for item in observations] == [
        "2026-01",
        "2026-02",
        "2026-03",
    ]
    assert observations[0].value == 51.0  # 默认值 50.0 + 输入位置 1


def test_load_observations_rejects_duplicate_period(tmp_path) -> None:
    chart = tmp_path / "chart.json"
    chart.write_text(
        json.dumps(_make_payload(["2026-01", "2026-01"])),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate UAE PMI period"):
        source.load_observations(chart)


def test_load_observations_rejects_non_month_start(tmp_path) -> None:
    payload = [
        {
            "series": [
                {
                    "serie": {
                        "data": [[50.0, 0, None, "2026-01-15"]],
                        "source": "S&P Global",
                        "frequency": "monthly",
                        "country": "United Arab Emirates",
                        "unit": "points",
                    }
                }
            ]
        }
    ]
    chart = tmp_path / "chart.json"
    chart.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="not month-start"):
        source.load_observations(chart)


def test_update_roundtrip_loads_monthly_table(tmp_path, monkeypatch) -> None:
    """解析 -> 入库往返：period 为月末、value 保留一位小数、字典一行。"""

    periods = _recent_periods(30)
    chart = tmp_path / "tradingeconomics_chart.json"
    chart.write_text(json.dumps(_make_payload(periods)), encoding="utf-8")
    metadata_path = tmp_path / "source_metadata.json"
    _write_metadata(metadata_path, periods)
    monkeypatch.setattr(source, "CHART_PATH", chart)
    monkeypatch.setattr(source, "METADATA_PATH", metadata_path)
    report_path = tmp_path / "quality_report.json"
    monkeypatch.setattr(source, "REPORT_PATH", report_path)

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = source.update(con, skip_download=True)

    assert outcome["status"] == "ok"
    assert outcome["rows"] == 30

    rows = con.execute(
        "SELECT period, value FROM pmi_monthly ORDER BY period"
    ).fetchall()
    assert len(rows) == 30
    last_year, last_month = (int(x) for x in periods[-1].split("-"))
    assert rows[-1][0] == date(
        last_year, last_month, calendar.monthrange(last_year, last_month)[1]
    )
    # 最新一期 value = 50.0 + 29 % 5 = 54.0
    assert rows[-1][1] == 54.0

    dictionary_row = con.execute(
        "SELECT indicator_name, frequency, unit, source, type, industry "
        "FROM meta_indicator_dictionary WHERE indicator_name = ?",
        [source.INDICATOR_NAME],
    ).fetchone()
    assert dictionary_row == (
        source.INDICATOR_NAME,
        "月",
        "点",
        source.SOURCE_LABEL,
        "指数",
        "宏观",
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    con.close()


def test_update_rounds_values_to_one_decimal(tmp_path, monkeypatch) -> None:
    """52.74 -> 52.7：与旧脚本一位小数舍入一致。"""

    periods = _recent_periods(24)
    values = [50.0] * 24
    values[-1] = 52.74
    chart = tmp_path / "tradingeconomics_chart.json"
    chart.write_text(json.dumps(_make_payload(periods, values)), encoding="utf-8")
    metadata_path = tmp_path / "source_metadata.json"
    _write_metadata(metadata_path, periods)
    monkeypatch.setattr(source, "CHART_PATH", chart)
    monkeypatch.setattr(source, "METADATA_PATH", metadata_path)
    monkeypatch.setattr(source, "REPORT_PATH", tmp_path / "quality_report.json")

    con = db.connect(":memory:")
    db.init_schema(con)
    source.update(con, skip_download=True)

    value = con.execute(
        "SELECT value FROM pmi_monthly ORDER BY period DESC LIMIT 1"
    ).fetchone()[0]
    con.close()
    assert value == 52.7


def test_target_is_current_matches_sheet(tmp_path) -> None:
    observations = [
        source.PmiObservation(period="2026-07", value=52.7),
        source.PmiObservation(period="2026-06", value=55.0),
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_LSEG"
    sheet.append([source.SOURCE_LABEL, None])
    sheet.append(["指标名称", source.INDICATOR_NAME])
    sheet.append(["频率", "月"])
    sheet.append(["单位", "点"])
    sheet.append(["来源", source.SOURCE_LABEL])
    sheet.append(["更新时间", datetime(2026, 8, 13)])
    sheet.append([datetime(2026, 7, 31), 52.7])
    sheet.append([datetime(2026, 6, 30), 55.0])
    target = tmp_path / "阿联酋.xlsx"
    workbook.save(target)
    workbook.close()

    assert source.target_is_current(target, observations)


def test_target_is_current_false_on_value_change(tmp_path) -> None:
    observations = [source.PmiObservation(period="2026-07", value=52.7)]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_LSEG"
    sheet.append([source.SOURCE_LABEL, None])
    sheet.append(["指标名称", source.INDICATOR_NAME])
    sheet.append(["频率", "月"])
    sheet.append(["单位", "点"])
    sheet.append(["来源", source.SOURCE_LABEL])
    sheet.append(["更新时间", datetime(2026, 8, 13)])
    sheet.append([datetime(2026, 7, 31), 53.0])
    target = tmp_path / "阿联酋.xlsx"
    workbook.save(target)
    workbook.close()

    assert not source.target_is_current(target, observations)
