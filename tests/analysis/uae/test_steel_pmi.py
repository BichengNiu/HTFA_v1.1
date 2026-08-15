"""Tests for the steel-price and PMI panels."""

from io import BytesIO

import pandas as pd
import pytest

from dashboard.analysis.uae.government_finance.pmi import (
    PMI_INDICATOR,
    build_pmi_figure,
    display_pmi_values,
    load_pmi_data,
)
from dashboard.analysis.uae.government_finance.search_index import (
    START_YEAR,
    VISA_UAE_COLUMN,
    WORK_DUBAI_COLUMN,
    WORK_UAE_COLUMN,
    build_search_index_figure,
    display_search_index_values,
)
from dashboard.analysis.uae.government_finance.steel import (
    EN_BEAMS_INDICATOR,
    REBAR_INDICATOR,
    build_steel_figure,
    display_steel_values,
    interpolate_steel_values,
    load_steel_data,
)

STEEL_SHEET = "月度_MEsteel"
PMI_SHEET = "月度_LSEG"


def _steel_workbook_bytes() -> bytes:
    dates = pd.date_range("2025-01-31", periods=8, freq="ME")
    frame = pd.DataFrame(
        {
            "日期": dates,
            REBAR_INDICATOR: [600, 610, None, 630, 640, None, 660, 670],
            EN_BEAMS_INDICATOR: [900, 910, 920, None, 940, 950, None, None],
        }
    )
    metadata = pd.DataFrame(
        [
            ["MEsteel", None, None, None, None],
            ["指标名称", REBAR_INDICATOR, EN_BEAMS_INDICATOR, None, None],
            ["频率", "月", "月", None, None],
            ["单位", "美元/吨", "美元/吨", None, None],
            ["来源", "MEsteel（CFR/CPT UAE）", "MEsteel（CFR/CPT UAE）", None, None],
            ["更新时间", "2026-08-13", "2026-08-13", None, None],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            frame.rename(columns={"日期": 0}).set_axis(range(3), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name=STEEL_SHEET,
            header=False,
            index=False,
        )
    return buffer.getvalue()


def _pmi_workbook_bytes() -> bytes:
    dates = pd.date_range("2025-01-31", periods=5, freq="ME")
    frame = pd.DataFrame({"日期": dates, PMI_INDICATOR: [51.0, 52.0, 50.5, 53.0, 52.2]})
    metadata = pd.DataFrame(
        [
            ["S&P Global / Trading Economics（公开样本）", None],
            ["指标名称", PMI_INDICATOR],
            ["频率", "月"],
            ["单位", "点"],
            ["来源", "S&P Global / Trading Economics（公开样本）"],
            ["更新时间", "2026-08-13"],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            frame.rename(columns={"日期": 0}).set_axis(range(2), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name=PMI_SHEET,
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_steel_loader_reads_rebar_and_en_beams() -> None:
    data = load_steel_data(_steel_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == ["螺纹钢", "EN及UB/UC型钢梁和槽钢"]
    assert data.values.index.min() == pd.Timestamp("2025-01-31")
    assert data.values.index.max() == pd.Timestamp("2025-08-31")
    assert {item.source for item in data.metadata.values()} == {
        "MEsteel（CFR/CPT UAE）"
    }


def test_steel_polynomial_interpolation_fills_internal_and_trailing_gaps() -> None:
    data = load_steel_data(_steel_workbook_bytes(), file_name="test.xlsx")

    interpolated = interpolate_steel_values(data.values)

    assert not interpolated.isna().any().any()
    rebar = interpolated["螺纹钢"]
    assert rebar.loc["2025-03-31"] > 610
    assert rebar.loc["2025-03-31"] < 630
    assert rebar.loc["2025-06-30"] > 640
    assert rebar.loc["2025-06-30"] < 660
    assert rebar.loc["2025-08-31"] > 660
    assert interpolated["EN及UB/UC型钢梁和槽钢"].loc["2025-04-30"] > 910
    assert interpolated["EN及UB/UC型钢梁和槽钢"].loc["2025-04-30"] < 940


def test_steel_display_frame_is_fully_interpolated() -> None:
    data = load_steel_data(_steel_workbook_bytes(), file_name="test.xlsx")

    display = display_steel_values(data.values)

    assert not display.isna().any().any()
    assert display.index.max() == pd.Timestamp("2025-08-31")


def test_steel_figure_plots_two_lines_on_one_axis() -> None:
    data = load_steel_data(_steel_workbook_bytes(), file_name="test.xlsx")

    figure = build_steel_figure(
        data.values,
        title="阿联酋钢材进口报价",
        source_text="MEsteel",
    )

    assert len(figure.axes) == 1
    lines = figure.axes[0].get_lines()
    assert [line.get_label() for line in lines] == ["螺纹钢", "EN及UB/UC型钢梁和槽钢"]
    assert figure.axes[0].get_ylabel() == "美元/吨"
    assert any(text.get_text() == "数据来源：MEsteel" for text in figure.texts)


def test_pmi_loader_reads_headline_index() -> None:
    data = load_pmi_data(_pmi_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [PMI_INDICATOR]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    assert data.values.loc["2025-05-31", PMI_INDICATOR] == pytest.approx(52.2)


def test_pmi_display_windows_to_recent_months() -> None:
    data = load_pmi_data(_pmi_workbook_bytes(), file_name="test.xlsx")

    display = display_pmi_values(data.values)

    assert display.index.max() == pd.Timestamp("2025-05-31")
    assert not display.empty


def test_pmi_figure_plots_single_line() -> None:
    data = load_pmi_data(_pmi_workbook_bytes(), file_name="test.xlsx")

    figure = build_pmi_figure(
        data.values,
        title="阿联酋非油私营部门PMI",
        source_text="S&P Global",
    )

    assert len(figure.axes) == 1
    lines = figure.axes[0].get_lines()
    assert [line.get_label() for line in lines] == [PMI_INDICATOR]
    assert figure.axes[0].get_ylabel() == "点"
    assert any(text.get_text() == "数据来源：S&P Global" for text in figure.texts)


def _search_index_frame() -> pd.DataFrame:
    dates = pd.date_range("2022-06-01", periods=20, freq="MS")
    return pd.DataFrame(
        {
            WORK_DUBAI_COLUMN: range(20),
            WORK_UAE_COLUMN: [5 + index * 0.5 for index in range(20)],
            VISA_UAE_COLUMN: range(50, 70),
        },
        index=pd.DatetimeIndex(dates),
    )


def test_search_index_display_filters_to_start_year() -> None:
    values = _search_index_frame()

    display = display_search_index_values(values)

    assert display.index.min() == pd.Timestamp(START_YEAR, 1, 1)
    assert display.index.max() == values.index.max()


def test_search_index_figure_standardizes_series_on_one_axis() -> None:
    values = _search_index_frame()

    figure = build_search_index_figure(
        values,
        title="阿联酋工作与签证谷歌搜索热度",
        source_text="Google 趋势",
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    lines = [
        line
        for line in axis.get_lines()
        if not line.get_label().startswith("_")
    ]
    assert [line.get_label() for line in lines] == [
        "搜索“在迪拜工作”",
        "搜索“在阿联酋工作”",
        "搜索“阿联酋签证”",
    ]
    for line in lines:
        ydata = pd.Series(line.get_ydata(), dtype=float).dropna()
        assert ydata.mean() == pytest.approx(0.0, abs=1e-9)
        assert ydata.std() == pytest.approx(1.0)
    assert axis.get_ylabel() == "标准化搜索指数"
    assert any(text.get_text() == "数据来源：Google 趋势" for text in figure.texts)