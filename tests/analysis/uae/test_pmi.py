"""Tests for the PMI and search-index panels."""

from io import BytesIO

import pandas as pd
import pytest

from tests.analysis.uae._helpers import report_source

from htfa.monitoring.uae.government_finance.pmi import (
    PMI_INDICATOR,
    build_pmi_figure,
    display_pmi_values,
    load_pmi_data,
)
from htfa.monitoring.uae.government_finance.search_index import (
    SEARCH_SHEET,
    SEARCH_SERIES,
    START_YEAR,
    WORK_DUBAI_COLUMN,
    WORK_UAE_COLUMN,
    build_search_index_figure,
    display_search_index_values,
    load_search_index_data,
)

PMI_SHEET = "月度_LSEG"


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


def test_pmi_loader_reads_headline_index() -> None:
    data = load_pmi_data(report_source(_pmi_workbook_bytes()))

    assert data.values.columns.tolist() == [PMI_INDICATOR]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    assert data.values.loc["2025-05-31", PMI_INDICATOR] == pytest.approx(52.2)


def test_pmi_display_windows_to_recent_months() -> None:
    data = load_pmi_data(report_source(_pmi_workbook_bytes()))

    display = display_pmi_values(data.values)

    assert display.index.max() == pd.Timestamp("2025-05-31")
    assert not display.empty


def test_pmi_figure_plots_single_line() -> None:
    data = load_pmi_data(report_source(_pmi_workbook_bytes()))

    figure = build_pmi_figure(
        data.values,
        title="阿联酋非油私营部门PMI",
        source_text="S&P Global",
    )

    assert len(figure.axes) == 1
    lines = figure.axes[0].get_lines()
    assert [line.get_label() for line in lines] == [PMI_INDICATOR]
    assert figure.axes[0].get_ylabel() == "点"
    # 单序列图不需要图例
    assert len(figure.legends) == 0
    assert figure.axes[0].get_legend() is None
    assert any(text.get_text() == "数据来源：标普全球" for text in figure.texts)


def _search_index_frame() -> pd.DataFrame:
    dates = pd.date_range("2022-06-01", periods=20, freq="MS")
    return pd.DataFrame(
        {
            WORK_DUBAI_COLUMN: range(20),
            WORK_UAE_COLUMN: [5 + index * 0.5 for index in range(20)],
        },
        index=pd.DatetimeIndex(dates),
    )


def _search_index_workbook_bytes() -> bytes:
    """构造包含月度工作搜索热度 sheet 的最小工作簿。"""

    indicators = [
        "阿联酋:Google搜索热度(work in dubai)",
        "阿联酋:Google搜索热度(work in uae)",
    ]
    rows = [
        ["Google Trends", None, None],
        ["指标名称", *indicators],
        ["频率", "月", "月"],
        ["单位", "指数", "指数"],
        ["来源", "Google Trends", "Google Trends"],
        ["更新时间", "2026-08-20", "2026-08-20"],
        [pd.Timestamp("2026-02-01"), 0, 8],
        [pd.Timestamp("2026-01-01"), 7, 0],
    ]
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(
            writer,
            sheet_name=SEARCH_SHEET,
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_search_index_loader_reads_workbook_sheet_and_preserves_zero() -> None:
    data = load_search_index_data(
        report_source(_search_index_workbook_bytes()),
    )

    assert data.columns.tolist() == [WORK_DUBAI_COLUMN, WORK_UAE_COLUMN]
    assert data.index.tolist() == [
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-02-01"),
    ]
    assert data.loc["2026-01-01", WORK_UAE_COLUMN] == 0
    assert data.loc["2026-02-01", WORK_DUBAI_COLUMN] == 0


def test_search_index_display_filters_to_start_year() -> None:
    values = _search_index_frame()

    display = display_search_index_values(values)

    assert display.index.min() == pd.Timestamp(START_YEAR, 1, 31)
    assert display.index.max().to_period("M") == values.index.max().to_period("M")


@pytest.mark.parametrize("length", [1, 12])
def test_search_index_does_not_substitute_raw_values_for_undefined_z_scores(length):
    values = pd.DataFrame({WORK_DUBAI_COLUMN: 5.0, WORK_UAE_COLUMN: 10.0},
                          index=pd.date_range("2026-01-31", periods=length, freq="ME"))
    with pytest.raises(ValueError, match="无法计算标准化指数"):
        display_search_index_values(values)


def test_search_index_month_start_observations_align_with_september_tick() -> None:
    values = pd.DataFrame(
        {
            WORK_DUBAI_COLUMN: range(45),
            WORK_UAE_COLUMN: range(45, 90),
        },
        index=pd.date_range("2023-01-01", periods=45, freq="MS"),
    )

    display = display_search_index_values(values)
    figure = build_search_index_figure(
        values, title="搜索热度", source_text="谷歌趋势"
    )

    assert values.index.max() == pd.Timestamp("2026-09-01")
    assert display.index.max() == pd.Timestamp("2026-09-30")
    assert [display[f"{label}（原始指数）"].iloc[-1] for _, label in SEARCH_SERIES] == values.iloc[-1].tolist()
    axis = figure.axes[0]
    for line in axis.get_lines():
        if not line.get_label().startswith("_"):
            assert pd.Timestamp(line.get_xdata()[-1]) == pd.Timestamp("2026-09-30")
    assert axis.get_xticklabels()[-1].get_text() == "9月"


def test_search_index_figure_standardizes_series_on_one_axis() -> None:
    values = _search_index_frame()
    download = display_search_index_values(values)

    figure = build_search_index_figure(
        values,
        title="阿联酋工作谷歌搜索热度",
        source_text="Google 趋势",
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    lines = [
        line
        for line in axis.get_lines()
        if line.get_label() and not line.get_label().startswith("_")
    ]
    assert [line.get_label() for line in lines] == [
        "搜索“在迪拜工作”",
        "搜索“在阿联酋工作”",
    ]
    for line in lines:
        ydata = pd.Series(line.get_ydata(), dtype=float).dropna()
        assert ydata.mean() == pytest.approx(0.0, abs=1e-9)
        assert ydata.std() == pytest.approx(1.0)
        label = line.get_label()
        pd.testing.assert_series_equal(
            download[label],
            pd.Series(line.get_ydata(), index=pd.DatetimeIndex(line.get_xdata())),
            check_names=False, check_freq=False,
        )
        smoothed = download[f"{label}（平滑指数）"]
        pd.testing.assert_series_equal(download[label],
            (smoothed - smoothed.mean()) / smoothed.std(), check_names=False)
    assert axis.get_ylabel() == "标准化指数"
    assert any(text.get_text() == "数据来源：谷歌趋势" for text in figure.texts)
