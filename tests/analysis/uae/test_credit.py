"""Tests for the CBUAE foreign-inflow and private-credit panels."""

from io import BytesIO

import pandas as pd
import pytest

from tests.analysis.uae._helpers import data_lines
from htfa.monitoring.uae.government_finance.credit import (
    BUSINESS_INDUSTRIAL,
    BUSINESS_INDUSTRIAL_DISPLAY,
    FOREIGN_CURRENCIES,
    FOREIGN_CURRENCIES_DISPLAY,
    FOREIGN_LIABILITIES,
    FOREIGN_LIABILITIES_DISPLAY,
    FOREIGN_SERIES,
    INDIVIDUAL,
    INDIVIDUAL_DISPLAY,
    NONRESIDENT_CORPORATE,
    NONRESIDENT_GOVERNMENT,
    NONRESIDENT_INDIVIDUALS,
    NONRESIDENT_DEPOSITS,
    PRIVATE_CORPORATE,
    PRIVATE_CORPORATE_DISPLAY,
    PRIVATE_CREDIT_SERIES,
    build_foreign_inflow_figure,
    build_private_credit_yoy_figure,
    load_foreign_inflow_data,
    load_private_credit_data,
)


def _workbook_bytes() -> bytes:
    """构造含外资流入（外债/外币/非居民三组分）+ 企业/居民/工商业信贷的迷你月度_CBUAE。"""

    dates = pd.date_range("2024-05-31", periods=14, freq="ME")
    indicator_columns = [
        "日期",
        FOREIGN_LIABILITIES,
        FOREIGN_CURRENCIES,
        NONRESIDENT_CORPORATE,
        NONRESIDENT_INDIVIDUALS,
        NONRESIDENT_GOVERNMENT,
        PRIVATE_CORPORATE,
        INDIVIDUAL,
        BUSINESS_INDUSTRIAL,
    ]
    metadata = pd.DataFrame(
        [
            ["CBUAE", *([None] * (len(indicator_columns) - 1))],
            ["指标名称", *indicator_columns[1:]],
            ["频率", *(["月"] * (len(indicator_columns) - 1))],
            ["单位", *(["百万迪拉姆"] * (len(indicator_columns) - 1))],
            ["来源", *(["CBUAE"] * (len(indicator_columns) - 1))],
            ["更新时间", *(["2026-08-17"] * (len(indicator_columns) - 1))],
        ]
    )
    data = pd.DataFrame(
        {
            "日期": dates,
            FOREIGN_LIABILITIES: [1_000_000.0] * 13 + [1_100_000.0],
            FOREIGN_CURRENCIES: [900_000.0] * 13 + [990_000.0],
            NONRESIDENT_CORPORATE: [60_000.0] * 13 + [66_000.0],
            NONRESIDENT_INDIVIDUALS: [30_000.0] * 13 + [33_000.0],
            NONRESIDENT_GOVERNMENT: [10_000.0] * 13 + [11_000.0],
            PRIVATE_CORPORATE: [1000.0] * 13 + [1100.0],
            INDIVIDUAL: [500.0] * 13 + [550.0],
            BUSINESS_INDUSTRIAL: [2000.0] * 13 + [2200.0],
        }
    )
    rows = pd.concat(
        [
            metadata,
            data.rename(columns={"日期": 0}).set_axis(
                range(len(indicator_columns)), axis=1
            ),
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


def test_foreign_inflow_loader_reads_three_indicators() -> None:
    data = load_foreign_inflow_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        FOREIGN_LIABILITIES_DISPLAY,
        FOREIGN_CURRENCIES_DISPLAY,
        NONRESIDENT_DEPOSITS,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-06-30")
    assert data.metadata[FOREIGN_LIABILITIES_DISPLAY].source == "CBUAE"
    assert data.metadata[FOREIGN_LIABILITIES_DISPLAY].unit == "百万迪拉姆"
    # 外国主体存款 = 非居民私人企业 + 个人 + 政府及非商业实体
    assert data.values.loc["2025-06-30", NONRESIDENT_DEPOSITS] == pytest.approx(
        110_000.0
    )
    assert NONRESIDENT_DEPOSITS not in data.metadata


def test_private_credit_loader_reads_corporate_individual_and_business() -> None:
    data = load_private_credit_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        PRIVATE_CORPORATE_DISPLAY,
        INDIVIDUAL_DISPLAY,
        BUSINESS_INDUSTRIAL_DISPLAY,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-06-30")


def test_foreign_inflow_figure_renders_yoy() -> None:
    data = load_foreign_inflow_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_foreign_inflow_figure(
        data.values,
        title="外资流入同比",
        source_text="CBUAE",
    )

    axis = figure.axes[0]
    lines = data_lines(axis)
    assert [line.get_label() for line in lines] == list(FOREIGN_SERIES)
    # 模板色板接管配色：黑 / 深蓝 / 灰
    assert [line.get_color() for line in lines] == [
        "#141414",
        "#1f4e79",
        "#888888",
    ]
    assert axis.get_ylabel() == "%"
    assert [line.get_ydata()[-1] for line in lines] == pytest.approx(
        [10.0, 10.0, 10.0]
    )
    assert any(text.get_text() == "数据来源：阿联酋央行" for text in figure.texts)
    # 严格遵从模板：同比图不再画 y=0 参考线
    assert not any(
        len(line.get_ydata()) >= 2 and set(line.get_ydata()) == {0.0}
        for line in axis.get_lines()
    )
    # 模板图例挂在参考轴上，图例线型与数据线一一对应
    legend_handles = axis.get_legend().get_lines()
    assert len(legend_handles) == len(lines)
    assert [h.get_color() for h in legend_handles] == [l.get_color() for l in lines]
    assert [h.get_linestyle() for h in legend_handles] == [
        l.get_linestyle() for l in lines
    ]


def test_private_credit_figure_renders_yoy() -> None:
    data = load_private_credit_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_private_credit_yoy_figure(
        data.values,
        title="企业及居民信贷同比",
        source_text="CBUAE",
    )

    axis = figure.axes[0]
    lines = data_lines(axis)
    assert [line.get_label() for line in lines] == list(PRIVATE_CREDIT_SERIES)
    # 模板色板接管配色：黑 / 深蓝 / 灰
    assert [line.get_color() for line in lines] == [
        "#141414",
        "#1f4e79",
        "#888888",
    ]
    assert axis.get_ylabel() == "%"
    assert [line.get_ydata()[-1] for line in lines] == pytest.approx(
        [10.0, 10.0, 10.0]
    )
    # 严格遵从模板：同比图不再画 y=0 参考线
    assert not any(
        len(line.get_ydata()) >= 2 and set(line.get_ydata()) == {0.0}
        for line in axis.get_lines()
    )
    # 模板图例挂在参考轴上，图例线型与数据线一一对应
    legend_handles = axis.get_legend().get_lines()
    assert len(legend_handles) == len(lines)
    assert [h.get_color() for h in legend_handles] == [l.get_color() for l in lines]
    assert [h.get_linestyle() for h in legend_handles] == [
        l.get_linestyle() for l in lines
    ]
