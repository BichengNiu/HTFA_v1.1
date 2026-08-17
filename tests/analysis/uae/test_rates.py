"""Tests for the EIBOR / US monthly-mean rates panel (4 series)."""

from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from dashboard.analysis.uae.government_finance.rates import (
    EIBOR_ONEYEAR_DISPLAY,
    EIBOR_ONEYEAR_INDICATOR,
    EIBOR_OVERNIGHT_DISPLAY,
    EIBOR_OVERNIGHT_INDICATOR,
    RATES_SERIES,
    US_OVERNIGHT_DISPLAY,
    US_OVERNIGHT_INDICATOR,
    US_SOFR_12M_DISPLAY,
    US_SOFR_12M_INDICATOR,
    build_rates_figure,
    load_rates_data,
)
from dashboard.analysis.uae.plot_helpers import matching_line_handles


def _workbook_bytes() -> bytes:
    """构造迷你日度_Wind：阿联酋/美国隔夜与 1 年期利率，倒序存放日值。"""

    rows = [
        ["Wind", None, None, None, None],
        [
            "指标名称",
            EIBOR_OVERNIGHT_INDICATOR,
            EIBOR_ONEYEAR_INDICATOR,
            US_OVERNIGHT_INDICATOR,
            US_SOFR_12M_INDICATOR,
        ],
        ["频率", "日", "日", "月", "日"],
        ["单位", "%", "%", "%", "%"],
        ["来源", "阿联酋央行", "阿联酋央行", "根据新闻整理", "根据新闻整理"],
        ["更新时间", "2026-08-17", "2026-08-17", "2026-08-17", "2026-08-17"],
        # 新→旧倒序（与真实 sheet 一致），美国两条某日缺值
        [date(2026, 8, 2), 8.0, 7.0, 5.0, 4.0],
        [date(2026, 8, 1), 6.0, 5.0, 4.0, 3.0],
        [date(2026, 7, 20), 5.0, 4.0, 3.5, 2.5],
        [date(2026, 7, 15), 3.0, 2.0, None, None],
        [date(2026, 7, 10), 4.0, 3.0, 3.0, 2.0],
    ]
    frame = pd.DataFrame(rows, columns=range(5))
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(
            writer,
            sheet_name="日度_Wind",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_rates_loader_resamples_daily_to_monthly_mean() -> None:
    data = load_rates_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        EIBOR_OVERNIGHT_DISPLAY,
        EIBOR_ONEYEAR_DISPLAY,
        US_OVERNIGHT_DISPLAY,
        US_SOFR_12M_DISPLAY,
    ]
    assert list(data.values.index) == [
        pd.Timestamp("2026-07-31"),
        pd.Timestamp("2026-08-31"),
    ]
    # 7 月：阿联酋隔夜=(3+4+5)/3=4，1年=(2+3+4)/3=3；美国隔夜/SOFR=(3+3.5)/2、(2+2.5)/2
    assert data.values.loc["2026-07-31", EIBOR_OVERNIGHT_DISPLAY] == pytest.approx(4.0)
    assert data.values.loc["2026-07-31", EIBOR_ONEYEAR_DISPLAY] == pytest.approx(3.0)
    assert data.values.loc["2026-07-31", US_OVERNIGHT_DISPLAY] == pytest.approx(3.25)
    assert data.values.loc["2026-07-31", US_SOFR_12M_DISPLAY] == pytest.approx(2.25)
    # 8 月：隔夜=(6+8)/2=7，1年=(5+7)/2=6；美国隔夜/SOFR=(4+5)/2、(3+4)/2
    assert data.values.loc["2026-08-31", EIBOR_OVERNIGHT_DISPLAY] == pytest.approx(7.0)
    assert data.values.loc["2026-08-31", EIBOR_ONEYEAR_DISPLAY] == pytest.approx(6.0)
    assert data.values.loc["2026-08-31", US_OVERNIGHT_DISPLAY] == pytest.approx(4.5)
    assert data.values.loc["2026-08-31", US_SOFR_12M_DISPLAY] == pytest.approx(3.5)


def test_rates_figure_renders_four_monthly_mean_lines() -> None:
    data = load_rates_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_rates_figure(
        data.values,
        title="阿联酋与美国市场利率（隔夜、1年期）",
        source_text="阿联酋央行",
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    lines = matching_line_handles(
        axis, [display_name for display_name, _ in RATES_SERIES]
    )
    assert [line.get_label() for line in lines] == [
        EIBOR_OVERNIGHT_DISPLAY,
        EIBOR_ONEYEAR_DISPLAY,
        US_OVERNIGHT_DISPLAY,
        US_SOFR_12M_DISPLAY,
    ]
    # 阿联酋两条黑线（隔夜实线、1年虚线），美国两条深蓝线（隔夜实线、SOFR 1年虚线）
    assert [line.get_color() for line in lines] == [
        "#000000",
        "#000000",
        "#1F4E79",
        "#1F4E79",
    ]
    assert [line.get_linestyle() for line in lines] == [
        "-",
        "--",
        "-",
        "--",
    ]
    assert axis.get_ylabel() == "％"
    assert axis.get_title() == "阿联酋与美国市场利率（隔夜、1年期）"
    assert lines[0].get_ydata()[-1] == pytest.approx(7.0)
    assert any(text.get_text() == "数据来源：阿联酋央行" for text in figure.texts)
    # 图例线条必须与图中数据线一一对应（颜色、线型完全一致）
    legend_handles = figure.legends[0].get_lines()
    assert len(legend_handles) == len(lines)
    assert [handle.get_color() for handle in legend_handles] == [
        line.get_color() for line in lines
    ]
    assert [handle.get_linestyle() for handle in legend_handles] == [
        line.get_linestyle() for line in lines
    ]
