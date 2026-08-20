"""Tests for the Baker Hughes UAE monthly rig-count extractor."""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from source_baker_hughes import (  # noqa: E402
    INDICATORS,
    RigObservation,
    extract_uae_monthly,
    select_latest_workbook,
    target_is_current,
)


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
        [
            "Middle East",
            "UAE - ABU DHABI",
            "Oil",
            "Land",
            "Active Rigs",
            year,
            month,
            50,
        ]
    )
    sheet.append(
        [
            "Middle East",
            "UAE - ABU DHABI",
            "Gas",
            "Offshore",
            "Active Rigs",
            year,
            month,
            10,
        ]
    )
    sheet.append(
        [
            "Middle East",
            "UAE - DUBAI",
            "Oil",
            "Offshore",
            "Active Rigs",
            year,
            month,
            2,
        ]
    )
    sheet.append(
        [
            "Middle East",
            "SAUDI ARABIA",
            "Oil",
            "Land",
            "Operating Rigs",
            year,
            month,
            90,
        ]
    )
    workbook.save(path)
    workbook.close()


def test_extract_uae_monthly_aggregates_emirates_and_ignores_non_oil(
    tmp_path,
) -> None:
    source = tmp_path / "report.xlsx"
    _source_workbook(source)

    observations = extract_uae_monthly(source)

    assert observations == [
        RigObservation(
            period="2026-07",
            oil=Decimal("52"),
        )
    ]


def test_select_latest_workbook_uses_observation_month_not_filename(
    tmp_path,
) -> None:
    older = tmp_path / "z-later-looking-name.xlsx"
    newer = tmp_path / "a-earlier-looking-name.xlsx"
    _source_workbook(older, month=7)
    _source_workbook(newer, month=8)

    selected, observations, errors = select_latest_workbook(tmp_path)

    assert selected == newer
    assert observations[-1].period == "2026-08"
    assert errors == []


def test_target_is_current_compares_all_managed_series(tmp_path) -> None:
    target = tmp_path / "阿联酋.xlsx"
    observation = RigObservation(
        period="2026-07",
        oil=Decimal("52"),
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_贝克休斯"
    sheet.append(["Baker Hughes", *([None] * len(INDICATORS))])
    sheet.append(["指标名称", *(name for name, _ in INDICATORS)])
    sheet.append(["频率", *(["月"] * len(INDICATORS))])
    sheet.append(["单位", *(["台"] * len(INDICATORS))])
    sheet.append(["来源", *(["Baker Hughes"] * len(INDICATORS))])
    sheet.append(["更新时间", *([datetime(2026, 8, 12)] * len(INDICATORS))])
    sheet.append([datetime(2026, 7, 31), *observation.values])
    workbook.save(target)
    workbook.close()

    assert target_is_current(target, [observation])
