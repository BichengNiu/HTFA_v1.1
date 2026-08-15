"""Tests for the CBUAE government and government-related entity panel."""

from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboard.analysis.uae.government_finance import renderer
from dashboard.analysis.uae.government_finance.charts import (
    YOY_SERIES,
    build_government_finance_yoy_figure,
)
from dashboard.analysis.uae.government_finance.data import (
    GOVERNMENT_CREDIT,
    GOVERNMENT_DEPOSITS,
    GOVERNMENT_AND_STATE_CAPITAL_CREDIT,
    GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS,
    GRE_CREDIT,
    GRE_DEPOSITS,
    calculate_calendar_yoy,
    combine_government_and_state_capital,
    load_government_finance_data,
)
from dashboard.analysis.uae.government_finance.renderer import _render_charts


def _workbook_bytes() -> bytes:
    dates = pd.date_range("2024-05-31", periods=13, freq="ME")
    frame = pd.DataFrame(
        {
            "日期": dates,
            GOVERNMENT_DEPOSITS: [100_000.0] * 12 + [110_000.0],
            GRE_DEPOSITS: [200_000.0] * 12 + [240_000.0],
            GOVERNMENT_CREDIT: [300_000.0] * 12 + [390_000.0],
            GRE_CREDIT: [400_000.0] * 12 + [500_000.0],
        }
    )
    future = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2025-06-30", "2025-07-31"]),
            GOVERNMENT_DEPOSITS: [0, 0],
            GRE_DEPOSITS: [0, 0],
            GOVERNMENT_CREDIT: [0, 0],
            GRE_CREDIT: [0, 0],
        }
    )
    data = pd.concat([future, frame.iloc[::-1]], ignore_index=True)
    metadata = pd.DataFrame(
        [
            ["CBUAE", None, None, None, None],
            [
                "指标名称",
                GOVERNMENT_DEPOSITS,
                GRE_DEPOSITS,
                GOVERNMENT_CREDIT,
                GRE_CREDIT,
            ],
            ["频率", "月", "月", "月", "月"],
            ["单位", *("百万迪拉姆",) * 4],
            ["来源", *("CBUAE",) * 4],
            ["更新时间", *("2026-08-12",) * 4],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            data.rename(columns={"日期": 0}).set_axis(range(5), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name="月度_CBUAE",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_loader_reads_four_cbuae_indicators_and_ignores_zero_placeholders() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )

    assert data.values.columns.tolist() == [
        GOVERNMENT_DEPOSITS,
        GOVERNMENT_CREDIT,
        GRE_DEPOSITS,
        GRE_CREDIT,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    assert data.values.loc["2025-05-31", GOVERNMENT_DEPOSITS] == 110_000
    assert {item.source for item in data.metadata.values()} == {"CBUAE"}


def test_calendar_yoy_uses_the_matching_month_when_an_observation_is_missing() -> None:
    dates = pd.date_range("2024-04-30", "2025-05-31", freq="ME").difference(
        pd.DatetimeIndex(["2024-06-30"])
    )
    observations = pd.Series(200.0, index=dates)
    observations.loc["2024-04-30"] = 50.0
    observations.loc["2024-05-31"] = 100.0
    observations.loc["2025-05-31"] = 110.0
    values = observations.to_frame("指标")

    yoy = calculate_calendar_yoy(values)

    assert yoy.loc["2025-05-31", "指标"] == pytest.approx(10.0)


def test_combined_series_requires_both_government_and_gre_components() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )

    combined = combine_government_and_state_capital(data.values)

    assert combined.columns.tolist() == [
        GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS,
        GOVERNMENT_AND_STATE_CAPITAL_CREDIT,
    ]
    assert combined.loc["2025-05-31"].tolist() == [350_000.0, 890_000.0]


def test_yoy_chart_combines_two_state_capital_series_without_absolute_bars() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )

    figure = build_government_finance_yoy_figure(
        data.values,
        title="政府及国有资本存款与信贷同比",
        source_text="CBUAE",
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    lines = axis.get_lines()[: len(YOY_SERIES)]
    assert [line.get_label() for line in lines] == [spec[1] for spec in YOY_SERIES]
    assert [line.get_color() for line in lines] == [spec[2] for spec in YOY_SERIES]
    assert [line.get_linestyle() for line in lines] == [spec[3] for spec in YOY_SERIES]
    assert [line.get_ydata()[-1] for line in lines] == pytest.approx(
        [16.6666667, 27.1428571]
    )
    assert axis.get_ylabel() == "同比（%）"
    assert axis.get_title() == "政府及国有资本存款与信贷同比"
    assert all(spine.get_visible() for spine in axis.spines.values())
    assert {text.get_text() for text in figure.legends[0].get_texts()} == {
        spec[1] for spec in YOY_SERIES
    }
    assert any(text.get_text() == "数据来源：阿联酋央行" for text in figure.texts)


def test_yoy_chart_calculates_yoy_before_applying_three_year_window() -> None:
    dates = pd.date_range("2021-01-31", periods=49, freq="ME")
    values = pd.DataFrame(
        {
            GOVERNMENT_DEPOSITS: range(100_000, 149_000, 1_000),
            GOVERNMENT_CREDIT: range(200_000, 249_000, 1_000),
            GRE_DEPOSITS: range(300_000, 349_000, 1_000),
            GRE_CREDIT: range(400_000, 449_000, 1_000),
        },
        index=dates,
    )

    figure = build_government_finance_yoy_figure(
        values,
        title="政府及国有资本存款与信贷同比",
        source_text="CBUAE",
    )

    lines = figure.axes[0].get_lines()[: len(YOY_SERIES)]
    assert {len(line.get_xdata()) for line in lines} == {37}
    assert all(pd.notna(line.get_ydata()[0]) for line in lines)


def test_chart_row_renders_one_yoy_view_and_downloads_only_yoy_data() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )
    st_obj = MagicMock()

    _render_charts(st_obj, data, pd.Timestamp("2025-05-31"))

    assert st_obj.pyplot.call_count == 1
    assert st_obj.download_button.call_count == 1
    chart_data = st_obj.download_button.call_args.kwargs["data"].decode("utf-8-sig")
    assert "同比（%）" in chart_data
    assert "百万迪拉姆" not in chart_data
    figure = st_obj.pyplot.call_args.args[0]
    assert st_obj.pyplot.call_args.kwargs["bbox_inches"] is None
    assert len(figure.axes) == 1
    assert {
        len(line.get_xdata())
        for line in figure.axes[0].get_lines()[: len(YOY_SERIES)]
    } == {13}


def test_section_renders_infrastructure_and_labor_employment_subsections(
    monkeypatch,
) -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )
    monkeypatch.setattr(
        renderer,
        "_load_government_finance_cached",
        lambda content, file_name: data,
    )
    for loader_name in (
        "_load_pmi_cached",
        "_load_foreign_labor_cached",
        "_load_search_index_cached",
    ):
        monkeypatch.setattr(renderer, loader_name, lambda *args: object())
    for render_name in (
        "_render_charts",
        "_render_pmi_chart",
        "_render_foreign_labor_chart",
        "_render_search_index_chart",
    ):
        monkeypatch.setattr(renderer, render_name, lambda *args: None)
    st_obj = MagicMock()
    st_obj.columns.return_value = (MagicMock(), MagicMock())

    result = renderer.render_government_finance_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    calls = [call[0] for call in st_obj.method_calls]
    assert calls.count("divider") == 2
    assert calls.count("subheader") == 2
    assert calls.index("divider") < calls.index("subheader")
    assert [call.args[0] for call in st_obj.subheader.call_args_list] == [
        "财政支出和投资",
        "劳动就业",
    ]
