"""阿联酋油价、产量和石油收入面板测试。"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, call

import pandas as pd
import pytest
from matplotlib.text import Annotation

from htfa.monitoring.uae.oil import renderer
from htfa.monitoring.uae.periods import (
    common_latest_month,
    within_month_window,
)
from htfa.monitoring.uae.oil.charts import (
    DUBAI_PRICE_LABEL,
    build_oil_price_figure,
    build_oil_production_figure,
    build_oil_revenue_only_figure,
    build_oil_rig_count_figure,
)
from htfa.monitoring.uae.oil.data import load_oil_market_data
from htfa.monitoring.uae.oil.revenue import (
    DAYS_COLUMN,
    PRICE_CONTRIBUTION_COLUMN,
    PRICE_BENCHMARK_COLUMN,
    PRODUCTION_CONTRIBUTION_COLUMN,
    REVENUE_COLUMN,
    YOY_COLUMN,
    YTD_COLUMN,
    YTD_YOY_COLUMN,
    estimate_monthly_oil_revenue,
)


def test_oil_panel_requires_explicit_workbook_payload() -> None:
    st_obj = MagicMock()

    with pytest.raises(TypeError):
        renderer.render_oil_fiscal_panel(st_obj)


def test_common_latest_month_uses_the_earliest_indicator_cutoff() -> None:
    prices = pd.Series(
        [70.0, 71.0],
        index=pd.to_datetime(["2026-07-31", "2026-08-12"]),
    )
    production = pd.Series(
        [3_000_000, 3_100_000],
        index=pd.to_datetime(["2026-06-30", "2026-07-31"]),
    )
    rigs = pd.Series(
        [58, 59],
        index=pd.to_datetime(["2026-06-30", "2026-07-31"]),
    )

    cutoff = common_latest_month(
        [
            ("布伦特现货", prices),
            ("阿联酋原油产量", production),
            ("阿联酋石油活跃钻机数", rigs),
        ]
    )
    aligned_prices = within_month_window(
        prices,
        first_month=cutoff - 36,
        last_month=cutoff,
    )

    assert cutoff == pd.Period("2026-07", freq="M")
    assert aligned_prices.index.max() == pd.Timestamp("2026-07-31")


def _sheet_frame(
    *,
    dates: pd.DatetimeIndex,
    names: list[str],
    frequencies: list[str],
    units: list[str],
    sources: list[str],
    values: list[list[float]],
) -> pd.DataFrame:
    rows = [
        ["公开来源测试数据", *([None] * len(names))],
        ["指标名称", *names],
        ["频率", *frequencies],
        ["单位", *units],
        ["来源", *sources],
        ["更新时间", *([pd.Timestamp("2026-08-11")] * len(names))],
    ]
    rows.extend(
        [date, *row_values]
        for date, row_values in zip(dates, zip(*values))
    )
    return pd.DataFrame(rows)


def _workbook_bytes(
    *,
    production_units: tuple[str, ...] = ("桶/天",),
) -> bytes:
    daily_dates = pd.date_range("2025-12-12", periods=20, freq="D")
    monthly_dates = pd.date_range("2025-01-31", periods=12, freq="ME")
    daily = _sheet_frame(
        dates=daily_dates, names=["布伦特现货"],
        frequencies=["日度"], units=["美元/桶"],
        sources=["U.S. EIA"], values=[list(range(70, 90))],
    )
    dubai = _sheet_frame(
        dates=monthly_dates, names=["全球: 名义商品价格: 迪拜原油"],
        frequencies=["月度"], units=["美元/桶"],
        sources=["IMF PCPS"], values=[list(range(69, 81))],
    )
    monthly = _sheet_frame(
        dates=monthly_dates, names=["阿联酋原油产量"] * len(production_units),
        frequencies=["月度"] * len(production_units), units=list(production_units),
        sources=["OPEC"] * len(production_units),
        values=[[(3_000 + i * 10 if unit == "千桶/天" else 3_000_000 + i * 10_000)
                 for i in range(12)] for unit in production_units],
    )
    rigs = _sheet_frame(
        dates=monthly_dates, names=["阿联酋石油活跃钻机数"],
        frequencies=["月"], units=["台"], sources=["Baker Hughes"],
        values=[[48 + i for i in range(12)]],
    )
    content = BytesIO()
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        for sheet_name, frame in [("日度_EIA", daily), ("月度_Dubai", dubai),
                                  ("月度_OPEC", monthly), ("月度_贝克休斯", rigs)]:
            frame.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
    return content.getvalue()


def test_targeted_loader_reads_prices_and_production() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.prices.columns.tolist() == [
        "布伦特现货",
        "迪拜现货",
    ]
    assert data.prices["布伦特现货"].count() == 20
    assert data.production.name == "阿联酋原油产量"
    assert data.production.iloc[-1] == 3_110_000
    assert data.rig_count is not None
    assert data.rig_count.name == "阿联酋石油活跃钻机数"
    assert data.rig_count.iloc[-1] == 59
    assert data.metadata["迪拜现货"].frequency == "月度"
    assert data.metadata["阿联酋原油产量"].source == "OPEC"


def test_targeted_loader_selects_matching_unit_from_duplicate_name() -> None:
    data = load_oil_market_data(
        _workbook_bytes(production_units=("千桶/天", "桶/天")),
        file_name="duplicate-units.xlsx",
    )

    assert data.production.iloc[-1] == 3_110_000
    assert data.metadata["阿联酋原油产量"].unit == "桶/天"


def test_targeted_loader_rejects_duplicate_matching_production_columns() -> None:
    with pytest.raises(ValueError, match="包含重复目标指标"):
        load_oil_market_data(
            _workbook_bytes(production_units=("桶/天", "桶/天")),
            file_name="ambiguous-production.xlsx",
        )


def test_oil_overview_metrics_show_current_three_indicators() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")
    st_obj = MagicMock()
    st_obj.columns.return_value = [MagicMock() for _ in range(4)]

    renderer._render_oil_metrics(st_obj, data)

    labels = [call.args[0] for call in st_obj.metric.call_args_list]
    assert labels == [
        "布伦特现货",
        "阿联酋原油产量",
        "阿联酋石油活跃钻机数",
    ]
    st_obj.markdown.assert_not_called()


def test_revenue_metrics_include_year_to_date_yoy() -> None:
    dates = pd.date_range("2024-01-31", periods=13, freq="ME")
    prices = pd.DataFrame({"布伦特现货": [100.0] * 12 + [110.0]}, index=dates)
    production = pd.Series(
        [1_000_000] * 12 + [1_200_000],
        index=dates,
        name="阿联酋原油产量",
    )
    revenue = estimate_monthly_oil_revenue(prices, production)
    st_obj = MagicMock()
    st_obj.columns.return_value = [MagicMock() for _ in range(4)]

    renderer._render_revenue_metrics(st_obj, revenue)

    labels = [call.args[0] for call in st_obj.metric.call_args_list]
    assert labels == [
        "最新月估算石油收入",
            "2025 年石油累计收入",
            "石油收入月度同比",
            "石油收入年度累计同比",
    ]
    assert st_obj.metric.call_args_list[-1].args[1] == "+32.0%"


def test_oil_split_figures_are_single_series() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")
    revenue = estimate_monthly_oil_revenue(data.prices, data.production)
    figures = [
        (
            build_oil_production_figure(data.production.div(10_000), "OPEC MOMR"),
            True,
            data.production.dropna().size,
        ),
        (
            build_oil_rig_count_figure(data.rig_count, "Baker Hughes"),
            False,
            data.rig_count.dropna().size,
        ),
        (
            build_oil_revenue_only_figure(revenue, "OPEC MOMR、U.S. EIA"),
            True,
            len(revenue),
        ),
    ]
    titles = ["原油产量", "活动钻井机数", "石油收入"]

    for (figure, bars, expected_points), title in zip(figures, titles):
        assert len(figure.axes) == 1
        axis = figure.axes[0]
        assert axis.get_title() == title
        extreme_labels = [
            text
            for text in axis.texts
            if isinstance(text, Annotation)
        ]
        assert extreme_labels
        assert not any(
            text.get_text() in {"最高", "最低"}
            for text in axis.texts
        )
        numeric_values = [
            float(text.get_text().replace(",", ""))
            for text in extreme_labels
        ]
        assert numeric_values
        assert len(extreme_labels) <= 2
        assert all(text.get_bbox_patch() is not None for text in extreme_labels)
        if bars:
            assert len(axis.patches) == expected_points
            assert all(
                text.get_zorder() > max(patch.get_zorder() for patch in axis.patches)
                for text in extreme_labels
            )
        else:
            assert len(axis.get_lines()) == 1
            assert all(
                text.get_zorder() > axis.get_lines()[0].get_zorder()
                for text in extreme_labels
            )

    assert any(
        text.get_text() == "数据来源：欧佩克月度石油市场报告"
        for text in figures[0][0].texts
    )
    assert any(
        text.get_text() == "数据来源：欧佩克月度石油市场报告、美国能源信息署"
        for text in figures[2][0].texts
    )


def test_oil_price_figure_combines_brent_and_dubai_on_shared_usd_axis() -> None:
    dates = pd.date_range("2024-01-31", periods=13, freq="ME")
    revenue = pd.DataFrame(
        {"月均油价": [80.0 + index for index in range(13)]},
        index=dates,
    )
    dubai_price = pd.Series(
        [78.0 + index for index in range(13)],
        index=dates,
        name="迪拜现货",
    )

    figure = build_oil_price_figure(
        revenue,
        "U.S. EIA、IMF Primary Commodity Price System (PCPS)",
        dubai_price=dubai_price,
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    assert [line.get_label() for line in axis.get_lines()] == [
        "布伦特原油现货价",
        DUBAI_PRICE_LABEL,
    ]
    assert axis.get_ylabel() == "美元/桶"
    assert axis.get_title() == "布伦特与迪拜原油现货月均价格"
    assert axis.get_lines()[0].get_linestyle() == "-"
    assert axis.get_lines()[1].get_linestyle() == "--"
    from inspect import signature
    from Ts.TsPlots import plot_series
    from Ts.TsPlots.style import WHITE

    defaults = signature(plot_series).parameters
    assert all(
        line.get_linewidth() == pytest.approx(defaults["linewidth"].default)
        for line in axis.get_lines()
    )
    assert axis.get_lines()[0].get_marker() == "o"
    assert axis.get_lines()[1].get_marker() == "s"
    assert all(
        line.get_markersize() == pytest.approx(defaults["markersize"].default)
        for line in axis.get_lines()
    )
    assert axis.get_lines()[1].get_markerfacecolor() == WHITE
    assert {
        text.get_text() for text in axis.get_legend().get_texts()
    } == {"布伦特原油现货价", DUBAI_PRICE_LABEL}
    assert axis.get_lines()[0].get_ydata()[-1] == pytest.approx(92.0)
    assert axis.get_lines()[1].get_ydata()[-1] == pytest.approx(90.0)
    assert len(
        [text for text in axis.texts if isinstance(text, Annotation)]
    ) <= 4


def test_render_charts_uses_requested_two_by_two_rows(monkeypatch) -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")
    revenue = estimate_monthly_oil_revenue(data.prices, data.production)
    st_obj = MagicMock()
    st_obj.columns.side_effect = [
        [MagicMock(), MagicMock()],
        [MagicMock(), MagicMock()],
    ]
    monkeypatch.setattr(renderer, "render_pyplot_figure", lambda *args, **kwargs: None)
    monkeypatch.setattr(renderer, "render_chart_download", lambda *args, **kwargs: None)

    renderer._render_charts(st_obj, data, revenue)

    assert st_obj.columns.call_args_list == [
        call(2, gap="small"),
        call(2, gap="small"),
    ]


def test_monthly_revenue_calculates_yoy_and_contributions() -> None:
    dates = pd.date_range("2024-01-31", periods=13, freq="ME")
    prices = pd.DataFrame(
        {
            "穆尔班现货": [200.0] * 13,
            "迪拜现货": [300.0] * 13,
            "布伦特现货": [100.0] * 12 + [110.0],
        },
        index=dates,
    )
    production = pd.Series(
        [1_000_000] * 12 + [1_200_000],
        index=dates,
        name="阿联酋原油产量",
    )

    revenue = estimate_monthly_oil_revenue(prices, production)

    assert revenue[YOY_COLUMN].iloc[-1] == pytest.approx(32.0)
    assert revenue[PRICE_CONTRIBUTION_COLUMN].iloc[-1] == pytest.approx(11.0)
    assert revenue[PRODUCTION_CONTRIBUTION_COLUMN].iloc[-1] == pytest.approx(21.0)
    assert (
        revenue[PRICE_CONTRIBUTION_COLUMN].iloc[-1]
        + revenue[PRODUCTION_CONTRIBUTION_COLUMN].iloc[-1]
    ) == pytest.approx(revenue[YOY_COLUMN].iloc[-1])
    assert revenue[YTD_COLUMN].iloc[-1] == pytest.approx(40.92)
    assert revenue[YTD_YOY_COLUMN].iloc[-1] == pytest.approx(32.0)


def test_monthly_revenue_uses_only_brent_spot_and_calendar_days() -> None:
    dates = pd.to_datetime(["2024-01-31", "2024-02-29"])
    prices = pd.DataFrame(
        {
            "穆尔班现货": [None, 110.0],
            "迪拜现货": [100.0, 105.0],
            "布伦特现货": [90.0, 95.0],
        },
        index=dates,
    )
    production = pd.Series(
        [1_000_000, 1_000_000],
        index=pd.to_datetime(["2024-01-31", "2024-02-29"]),
        name="阿联酋原油产量",
    )

    revenue = estimate_monthly_oil_revenue(prices, production)

    assert revenue[PRICE_BENCHMARK_COLUMN].tolist() == ["布伦特现货", "布伦特现货"]
    assert revenue[DAYS_COLUMN].tolist() == [31, 29]
    assert revenue[REVENUE_COLUMN].iloc[0] == pytest.approx(27.9)
    assert revenue[REVENUE_COLUMN].iloc[1] == pytest.approx(27.55)
    assert revenue[YTD_COLUMN].iloc[-1] == pytest.approx(55.45)
