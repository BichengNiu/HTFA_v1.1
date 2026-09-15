"""阿联酋油价、产量和石油收入面板测试。"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, call

import numpy as np
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
    build_oil_market_figure,
    build_oil_price_figure,
    build_oil_production_figure,
    build_oil_revenue_figure,
    build_oil_revenue_only_figure,
    build_oil_rig_count_figure,
    plot_series,
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
        ["Wind", *([None] * len(names))],
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
    price_names = [
        "期货结算价(连续):布伦特原油",
        "全球:现货价:原油(英国布伦特Dtd)",
        "全球:现货价:原油(阿联酋迪拜)",
        "全球:现货均价:原油(阿联酋穆尔班)",
    ]
    daily = _sheet_frame(
        dates=daily_dates,
        names=price_names,
        frequencies=["日", "日", "日", "周"],
        units=["美元/桶"] * 4,
        sources=["ICE", "金联创", "金联创", "金联创"],
        values=[
            [0, *range(71, 90)],
            list(range(70, 90)),
            list(range(69, 89)),
            list(range(68, 88)),
        ],
    )
    monthly = _sheet_frame(
        dates=monthly_dates,
        names=["阿联酋:产量:原油"] * len(production_units),
        frequencies=["月"] * len(production_units),
        units=list(production_units),
        sources=["OPEC"] * len(production_units),
        values=[
            (
                [3_000 + index * 10 for index in range(12)]
                if unit == "千桶/天"
                else [3_000_000 + index * 10_000 for index in range(12)]
            )
            for unit in production_units
        ],
    )
    rigs = _sheet_frame(
        dates=pd.date_range("2025-01-31", periods=12, freq="ME"),
        names=["阿联酋石油活跃钻机数"],
        frequencies=["月"],
        units=["台"],
        sources=["Baker Hughes"],
        values=[[48 + index for index in range(12)]],
    )

    content = BytesIO()
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "指标名称": ["重复", "重复"],
                "类型": [None, None],
                "行业": [None, None],
                "数据来源": [None, None],
                "预测变量": [None, None],
            }
        ).to_excel(writer, sheet_name="指标字典", index=False)
        daily.to_excel(writer, sheet_name="日度_Wind", index=False, header=False)
        monthly.to_excel(writer, sheet_name="月度_Wind", index=False, header=False)
        rigs.to_excel(
            writer,
            sheet_name="月度_贝克休斯",
            index=False,
            header=False,
        )
    return content.getvalue()


def test_targeted_loader_reads_prices_and_production() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.prices.columns.tolist() == [
        "布伦特期货",
        "布伦特现货",
        "迪拜现货",
        "穆尔班现货",
    ]
    assert data.prices["布伦特期货"].count() == 19
    assert data.production.name == "阿联酋原油产量"
    assert data.production.iloc[-1] == 3_110_000
    assert data.rig_count is not None
    assert data.rig_count.name == "阿联酋石油活跃钻机数"
    assert data.rig_count.iloc[-1] == 59
    assert data.metadata["穆尔班现货"].frequency == "周"
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


def test_oil_overview_metrics_show_requested_four_indicators() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")
    st_obj = MagicMock()
    st_obj.columns.return_value = [MagicMock() for _ in range(4)]

    renderer._render_oil_metrics(st_obj, data)

    labels = [call.args[0] for call in st_obj.metric.call_args_list]
    assert labels == [
        "布伦特期货",
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


def test_oil_market_figure_combines_production_and_rigs() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_oil_market_figure(
        data.production,
        "OPEC、Baker Hughes",
        data.rig_count,
    )

    production_axis, rig_axis = figure.axes
    assert len(production_axis.patches) == len(data.production)
    assert production_axis.patches[-1].get_height() == 311.0
    assert len(rig_axis.get_lines()) == 1
    assert (
        rig_axis.get_lines()[0].get_label()
        == "阿联酋石油活跃钻机数"
    )
    assert rig_axis.get_lines()[0].get_ydata()[-1] == 59
    assert production_axis.get_ylabel() == "万桶/天"
    assert rig_axis.get_ylabel() == "台"
    assert production_axis.get_title() == "原油产量与活动钻机数"
    assert figure._suptitle is None
    assert production_axis.get_xticklabels()[-1].get_text() == "12月"
    # 模板 BottomLegend 挂在参考轴（主轴）上，双轴叠加自动追加（左轴/右轴）后缀
    bottom_legend = production_axis.get_legend()
    legend_labels = {
        text.get_text()
        for text in bottom_legend.get_texts()
    }
    assert legend_labels == {
        "阿联酋原油产量（左轴）",
        "阿联酋石油活跃钻机数（右轴）",
    }
    assert bottom_legend.get_bbox_to_anchor()._bbox.y0 < 0.2
    # 模板 draw_note_and_bottom_title 按图例/图注实测撑开底部边距。
    assert figure.subplotpars.bottom >= 0.25
    assert {text.get_text().strip() for text in production_axis.texts} >= {
        "2025年"
    }
    assert any(
        text.get_text() == "数据来源：欧佩克、贝克休斯"
        for text in figure.texts
    )


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
            build_oil_price_figure(
                revenue,
                "U.S. EIA",
                {"布伦特原油现货价": "百美元/桶"},
            ),
            False,
            len(revenue),
        ),
        (
            build_oil_revenue_only_figure(revenue, "OPEC MOMR、U.S. EIA"),
            True,
            len(revenue),
        ),
    ]
    titles = ["原油产量", "活动钻井机数", "石油价格", "石油收入"]

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

    price_figure = figures[2][0]
    assert price_figure.axes[0].get_ylabel() == "美元/桶"
    assert "百美元/桶" not in price_figure.axes[0].get_ylabel()
    assert any(
        text.get_text() == "数据来源：欧佩克月度石油市场报告"
        for text in figures[0][0].texts
    )
    assert any(
        text.get_text() == "数据来源：美国能源信息署"
        for text in price_figure.texts
    )
    assert any(
        text.get_text() == "数据来源：欧佩克月度石油市场报告、美国能源信息署"
        for text in figures[3][0].texts
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
        units={"布伦特原油现货价": "百美元/桶"},
        dubai_price=dubai_price,
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    assert [line.get_label() for line in axis.get_lines()] == [
        "布伦特原油现货价",
        DUBAI_PRICE_LABEL,
    ]
    assert axis.get_ylabel() == "美元/桶"
    assert axis.get_title() == "石油价格"
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


def test_oil_market_figure_marks_war_start_with_red_dashed_line() -> None:
    dates = pd.date_range("2025-12-31", periods=6, freq="ME")
    production = pd.Series(
        [3_000_000] * 6,
        index=dates,
        name="阿联酋原油产量",
    )

    figure = build_oil_market_figure(production, "OPEC")

    from matplotlib.colors import to_rgba
    from Ts.TsPlots.style import REFERENCE_LINE_COLOR

    expected = to_rgba(REFERENCE_LINE_COLOR)
    production_axis = figure.axes[0]
    war_lines = [
        line
        for line in production_axis.get_lines()
        if tuple(to_rgba(line.get_color())) == expected
    ]
    assert war_lines
    assert all(line.get_linestyle() == "--" for line in war_lines)
    # 单序列（只有产量柱、无钻机线）默认不显示图例，底部仅需容纳来源图注
    # 与年份标尺；只要有足够底部边距容纳图注即可。
    assert figure.subplotpars.bottom > 0.05
    assert any(
        text.get_text() == "<- 战争 ->"
        for text in production_axis.texts
    )


def test_oil_market_figure_skips_war_line_before_march_2026() -> None:
    dates = pd.date_range("2025-01-31", periods=12, freq="ME")
    production = pd.Series(
        [3_000_000] * 12,
        index=dates,
        name="阿联酋原油产量",
    )

    figure = build_oil_market_figure(production, "OPEC")

    from matplotlib.colors import to_rgba
    from Ts.TsPlots.style import REFERENCE_LINE_COLOR

    expected = to_rgba(REFERENCE_LINE_COLOR)
    production_axis = figure.axes[0]
    assert not [
        line
        for line in production_axis.get_lines()
        if tuple(to_rgba(line.get_color())) == expected
    ]
    assert not any(
        text.get_text() == "<- 战争 ->"
        for text in production_axis.texts
    )


def test_oil_figures_accept_ts_ndarray_axes(monkeypatch) -> None:
    original_plot_series = plot_series

    def plot_series_with_array_axis(*args, **kwargs):
        figure, axis = original_plot_series(*args, **kwargs)
        return figure, np.asarray([axis], dtype=object)

    monkeypatch.setattr(
        "htfa.monitoring.uae.oil.charts.plot_series",
        plot_series_with_array_axis,
    )
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")
    revenue = estimate_monthly_oil_revenue(data.prices, data.production)

    market_figure = build_oil_market_figure(
        data.production,
        "OPEC、Baker Hughes",
        data.rig_count,
    )
    revenue_figure = build_oil_revenue_figure(revenue, "金联创、OPEC")

    assert len(market_figure.axes) == 2
    assert len(revenue_figure.axes) == 2


def test_monthly_revenue_uses_only_brent_spot_and_calendar_days() -> None:
    dates = pd.to_datetime(["2024-01-15", "2024-02-15"])
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


def test_monthly_revenue_calculates_yoy_and_chart_axes() -> None:
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
    figure = build_oil_revenue_figure(revenue, "金联创、OPEC")

    assert revenue[YOY_COLUMN].iloc[-1] == pytest.approx(32.0)
    assert revenue[PRICE_CONTRIBUTION_COLUMN].iloc[-1] == pytest.approx(11.0)
    assert revenue[PRODUCTION_CONTRIBUTION_COLUMN].iloc[-1] == pytest.approx(21.0)
    assert (
        revenue[PRICE_CONTRIBUTION_COLUMN].iloc[-1]
        + revenue[PRODUCTION_CONTRIBUTION_COLUMN].iloc[-1]
    ) == pytest.approx(revenue[YOY_COLUMN].iloc[-1])
    assert revenue[YTD_COLUMN].iloc[-1] == pytest.approx(40.92)
    assert revenue[YTD_YOY_COLUMN].iloc[-1] == pytest.approx(32.0)
    price_axis, revenue_axis = figure.axes
    # 序列名为裸变量名，图例的（左轴/右轴）后缀由模板自动追加
    assert [line.get_label() for line in price_axis.get_lines()] == [
        "布伦特原油现货价",
    ]
    assert len(revenue_axis.patches) == len(revenue)
    assert revenue_axis.patches[-1].get_height() == pytest.approx(40.92)
    assert revenue_axis.get_ylabel() == "亿美元"
    assert price_axis.get_ylabel() == "美元/桶"
    assert price_axis.get_title() == "石油价格与石油收入"
    assert figure._suptitle is None
    assert price_axis.get_xticklabels()[-1].get_text() == "12月"
    legend_labels = {
        text.get_text() for text in price_axis.get_legend().get_texts()
    }
    assert legend_labels == {
        "布伦特原油现货价（左轴）",
        "石油收入（右轴）",
    }
    assert price_axis.get_legend().get_bbox_to_anchor()._bbox.y0 < 0.2
    assert figure.subplotpars.bottom >= 0.25
    assert len(price_axis.get_xticklabels()) <= 4
    assert {text.get_text().strip() for text in price_axis.texts} >= {
        "2024年",
        "2025年",
    }
    assert any(
        text.get_text() == "数据来源：金联创、欧佩克"
        for text in figure.texts
    )
