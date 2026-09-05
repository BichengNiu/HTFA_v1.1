"""Tests for shared UAE chart formatting helpers."""

from matplotlib.figure import Figure

import pytest

from htfa.monitoring.uae.plot_helpers import (
    format_compact_y_axis,
    source_note,
)


def test_compact_axis_converts_pre_scaled_dirham_units_once() -> None:
    figure = Figure()
    axis = figure.add_subplot(111)
    axis.plot([0, 1], [100_000, 200_000])
    axis.set_ylabel("百万迪拉姆")
    axis.set_ylim(0, 1_000_000)

    format_compact_y_axis(axis)

    assert axis.get_ylabel() == "万亿迪拉姆"
    assert axis.yaxis.get_major_formatter()(1_000_000, 0) == "1"


def test_compact_axis_uses_count_units_at_the_same_threshold_as_metrics() -> None:
    figure = Figure()
    axis = figure.add_subplot(111)
    axis.plot([0, 1], [1_000, 6_584])
    axis.set_ylabel("家")

    format_compact_y_axis(axis)

    assert axis.get_ylabel() == "万家"
    assert axis.yaxis.get_major_formatter()(10_000, 0) == "1"


@pytest.mark.parametrize(
    ("source", "translated"),
    [
        ("CBUAE", "阿联酋央行"),
        ("S&P Global", "标普全球"),
        ("Baker Hughes", "贝克休斯"),
        ("UAE Ministry of Finance (MOF GFS)", "阿联酋财政部"),
        ("IMF PortWatch (HDX mirror)", "国际货币基金组织港口监测"),
        (
            "US DOT BTS T-100 International Segment (All Carriers)",
            "美国交通部统计局 BTS T-100 国际航段",
        ),
        (
            "Dubai Customs Airway Bill Details（data.dubai 开放数据，ID 459114）",
            "迪拜海关航空运单明细",
        ),
        (
            "data.dubai Commerce Registry",
            "data.dubai 商业登记库",
        ),
    ],
)
def test_source_note_translates_workbook_sources(
    source: str,
    translated: str,
) -> None:
    assert source_note(source) == f"数据来源：{translated}"
