"""阿联酋油价、产量和石油收入面板测试。"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from dashboard.analysis.uae.oil import charts as oil_charts
from dashboard.analysis.uae.oil import renderer
from dashboard.analysis.uae.oil.charts import (
    build_oil_market_figure,
    build_oil_revenue_figure,
)
from dashboard.analysis.uae.oil.data import load_oil_market_data
from dashboard.analysis.uae.oil.revenue import (
    DAYS_COLUMN,
    PRICE_CONTRIBUTION_COLUMN,
    PRICE_BENCHMARK_COLUMN,
    PRODUCTION_CONTRIBUTION_COLUMN,
    REVENUE_COLUMN,
    YOY_COLUMN,
    YTD_COLUMN,
    estimate_monthly_oil_revenue,
)


def test_oil_panel_reports_missing_shared_workbook(monkeypatch) -> None:
    st_obj = MagicMock()
    monkeypatch.setattr(renderer, "_source_payload", lambda: None)

    result = renderer.render_oil_fiscal_panel(st_obj)

    assert result["status"] == "no_data"
    st_obj.subheader.assert_called_once_with("石油生产与收入")
    st_obj.info.assert_called_once()


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
    daily_dates = pd.date_range("2025-01-01", periods=20, freq="D")
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


def test_monitoring_requires_a_shared_upload(monkeypatch) -> None:
    monkeypatch.setattr(renderer, "get_shared_dataset_file", lambda: None)

    assert renderer._source_payload() is None


def test_oil_market_figure_combines_brent_and_production() -> None:
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_oil_market_figure(
        data.prices,
        data.production,
        "金联创、OPEC",
        data.rig_count,
    )

    price_axis, production_axis, rig_axis = figure.axes
    assert len(price_axis.get_lines()) == 1
    assert price_axis.get_lines()[0].get_label() == "布伦特原油现货价（左轴）"
    assert price_axis.get_lines()[0].get_color() == "#000000"
    assert price_axis.get_lines()[0].get_linestyle() == "--"
    assert len(production_axis.patches) == len(data.production)
    assert production_axis.patches[-1].get_height() == 311.0
    assert production_axis.patches[-1].get_facecolor() == pytest.approx(
        (184 / 255, 189 / 255, 198 / 255, 0.72)
    )
    assert production_axis.patches[-1].get_edgecolor() == pytest.approx(
        (107 / 255, 114 / 255, 128 / 255, 0.72)
    )
    assert len(rig_axis.get_lines()) == 1
    assert (
        rig_axis.get_lines()[0].get_label()
        == "阿联酋石油活跃钻机数（外右轴）"
    )
    assert rig_axis.get_lines()[0].get_color() == "#1F4E79"
    assert rig_axis.get_lines()[0].get_linestyle() == "-"
    assert rig_axis.get_lines()[0].get_ydata()[-1] == 59
    assert price_axis.get_ylabel() == "美元/桶"
    assert production_axis.get_ylabel() == "万桶/天"
    assert price_axis.get_title() == ""
    assert figure._suptitle.get_text() == "原油价格、产量与钻机数"
    legend_labels = [
        text.get_text()
        for text in figure.texts
        if text.get_text() in {
            "布伦特原油现货价（左轴）",
            "阿联酋原油产量（右轴）",
            "阿联酋石油活跃钻机数（外右轴）",
        }
    ]
    assert legend_labels == [
        "布伦特原油现货价（左轴）",
        "阿联酋原油产量（右轴）",
        "阿联酋石油活跃钻机数（外右轴）",
    ]
    assert any(
        text.get_text() == "数据来源：金联创、OPEC"
        for text in figure.texts
    )


def test_oil_figures_accept_ts_ndarray_axes(monkeypatch) -> None:
    original_plot_series = oil_charts.plot_series

    def plot_series_with_array_axis(*args, **kwargs):
        figure, axis = original_plot_series(*args, **kwargs)
        return figure, np.asarray([axis], dtype=object)

    monkeypatch.setattr(
        oil_charts,
        "plot_series",
        plot_series_with_array_axis,
    )
    data = load_oil_market_data(_workbook_bytes(), file_name="test.xlsx")
    revenue = estimate_monthly_oil_revenue(data.prices, data.production)

    market_figure = build_oil_market_figure(
        data.prices,
        data.production,
        "金联创、OPEC",
        data.rig_count,
    )
    revenue_figure = build_oil_revenue_figure(revenue, "金联创、OPEC")

    assert len(market_figure.axes) == 3
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
    rate_axis, revenue_axis = figure.axes
    assert [line.get_label() for line in rate_axis.get_lines()] == [
        "石油收入同比增速（右轴）",
        "油价拉动率（右轴）",
        "产量拉动率（右轴）",
    ]
    assert [line.get_color() for line in rate_axis.get_lines()] == [
        "#000000",
        "#000000",
        "#1F4E79",
    ]
    assert [line.get_linestyle() for line in rate_axis.get_lines()] == [
        "-",
        "--",
        ":",
    ]
    assert len(revenue_axis.patches) == len(revenue)
    assert revenue_axis.patches[-1].get_height() == pytest.approx(40.92)
    assert revenue_axis.patches[-1].get_facecolor() == pytest.approx(
        (184 / 255, 189 / 255, 198 / 255, 0.72)
    )
    assert revenue_axis.patches[-1].get_edgecolor() == pytest.approx(
        (107 / 255, 114 / 255, 128 / 255, 0.72)
    )
    assert revenue_axis.get_ylabel() == "亿美元"
    assert rate_axis.get_ylabel() == "拉动率/同比（%）"
    assert rate_axis.get_title() == ""
    assert figure._suptitle.get_text() == "估算石油收入"
    legend_labels = [text.get_text() for text in figure.legends[0].get_texts()]
    assert legend_labels == [
        "石油收入（左轴）",
        "石油收入同比增速（右轴）",
        "油价拉动率（右轴）",
        "产量拉动率（右轴）",
    ]
    assert any(
        text.get_text() == "数据来源：金联创、OPEC"
        for text in figure.texts
    )
