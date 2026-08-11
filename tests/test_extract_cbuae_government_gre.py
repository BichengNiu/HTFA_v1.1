"""Tests for the CBUAE government/GRE monthly-series extractor."""

from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook

from data.CBUAE.update_cbuae_monthly import (
    Observation,
    _normalize_label,
    add_missing_fallbacks,
    extract_wind_fallback,
    select_latest_vintages,
)


def _observation(
    period: str,
    value: str,
    source_period: str,
) -> Observation:
    values = (Decimal(value),) * 4
    return Observation(period, values, source_period, f"{source_period}.xlsx")


def test_normalize_label_handles_gre_parenthesis_spacing() -> None:
    """Both workbook spellings of the GRE credit row should match."""

    assert _normalize_label("Public Sector ( GREs )") == "public sector (gres)"
    assert _normalize_label("Public Sector (GREs)") == "public sector (gres)"


def test_select_latest_vintage_reports_revisions_and_gaps() -> None:
    """Later bulletins win and missing calendar months remain explicit."""

    observations = [
        _observation("2020-01", "1", "2020-01"),
        _observation("2020-01", "2", "2020-03"),
        _observation("2020-03", "3", "2020-03"),
    ]

    selected, missing, revised_periods = select_latest_vintages(
        observations,
        start_period="2020-01",
        end_period="2020-03",
    )

    assert [item.period for item in selected] == ["2020-01", "2020-03"]
    assert selected[0].values[0] == Decimal("2")
    assert missing == ["2020-02"]
    assert revised_periods == 1


def test_add_missing_fallbacks_does_not_override_primary() -> None:
    """Wind observations fill gaps without replacing official observations."""

    primary = [_observation("2020-01", "1", "2020-01")]
    fallback = [
        _observation("2019-12", "9", "2019-12"),
        _observation("2020-01", "8", "2020-01"),
        _observation("2020-02", "7", "2020-02"),
    ]

    merged, added = add_missing_fallbacks(
        primary,
        fallback,
        start_period="2019-12",
        end_period=None,
    )

    assert [item.period for item in merged] == ["2019-12", "2020-01", "2020-02"]
    assert merged[1].values[0] == Decimal("1")
    assert added == ["2019-12", "2020-02"]


def test_extract_wind_fallback_reads_named_monthly_columns(tmp_path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "月度_Wind"
    names = (
        "阿联酋:银行存款:居民存款:政府部门",
        "阿联酋:银行存款:居民存款:政府相关实体(政府持股超50%)",
        "阿联酋:信贷总额:国内信贷:政府部门",
        "阿联酋:信贷总额:国内信贷:公共部门(政府相关实体)",
    )
    sheet.append(["Wind", None, None, None, None])
    sheet.append(["指标名称", *names])
    sheet.append(["频率", "月", "月", "月", "月"])
    sheet.append(["单位", *("十亿阿联酋迪拉姆",) * 4])
    sheet.append(["来源", *("Wind",) * 4])
    sheet.append(["更新时间", *("2026-08-11",) * 4])
    sheet.append([datetime(2020, 2, 29), 263.9, 238.2, 231.5, 185.0])
    workbook_path = tmp_path / "wind.xlsx"
    workbook.save(workbook_path)
    workbook.close()

    observations = extract_wind_fallback(workbook_path)

    assert len(observations) == 1
    assert observations[0].period == "2020-02"
    assert observations[0].values == (
        Decimal("263900.000"),
        Decimal("238200.000"),
        Decimal("231500.000"),
        Decimal("185000.000"),
    )
