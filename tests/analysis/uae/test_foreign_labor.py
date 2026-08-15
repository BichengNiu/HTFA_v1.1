"""Tests for the foreign-labour companion chart."""

from io import BytesIO

import pandas as pd

from dashboard.analysis.uae.foreign_labor import (
    BANGLADESH_CLEARANCES,
    BANGLADESH_LABEL,
    FOREIGN_LABOR_SHEET,
    NEPAL_APPROVALS,
    NEPAL_LABEL,
    SERIES_SPECS,
    build_foreign_labor_figure,
    latest_common_month,
    load_foreign_labor_data,
)


def _workbook_bytes() -> bytes:
    dates = pd.date_range("2023-06-30", periods=38, freq="ME")[::-1]
    data = pd.DataFrame(
        {
            "日期": dates,
            NEPAL_APPROVALS: range(1_000, 1_000 + len(dates)),
            BANGLADESH_CLEARANCES: range(2_000, 2_000 + len(dates)),
        }
    )
    data.loc[len(data) - 1, BANGLADESH_CLEARANCES] = 0
    metadata = pd.DataFrame(
        [
            ["各国官方劳工输出登记/部署/审批数据", None, None],
            ["日期", NEPAL_APPROVALS, BANGLADESH_CLEARANCES],
            ["月", "月", "月"],
            ["日期", "人", "人"],
            ["各国官方劳工输出登记/部署/审批数据",
             "尼泊尔 DoFE monthly final labour approval",
             "孟加拉国 BMET/OEP Country Clearance"],
            ["更新时间", "2026-08-14", "2026-08-14"],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            data.rename(columns={"日期": 0}).set_axis(range(3), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name=FOREIGN_LABOR_SHEET,
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_loader_reads_the_two_requested_monthly_labour_series() -> None:
    data = load_foreign_labor_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        NEPAL_APPROVALS,
        BANGLADESH_CLEARANCES,
    ]
    assert data.values.index.max() == pd.Timestamp("2026-07-31")
    assert data.values.loc["2026-07-31", BANGLADESH_CLEARANCES] != 0
    assert set(item.source for item in data.metadata.values()) == {
        "尼泊尔 DoFE monthly final labour approval",
        "孟加拉国 BMET/OEP Country Clearance",
    }


def test_chart_uses_the_latest_common_month_and_two_requested_lines() -> None:
    data = load_foreign_labor_data(_workbook_bytes(), file_name="test.xlsx")

    assert latest_common_month(data.values) == pd.Period("2026-07", freq="M")
    figure = build_foreign_labor_figure(
        data.values,
        title="尼泊尔批准（含再入境）与孟加拉出境许可",
        source_text="尼泊尔 DoFE monthly final labour approval；"
        "孟加拉国 BMET/OEP Country Clearance",
    )

    nepal_axis, bangladesh_axis = figure.axes
    assert len(nepal_axis.containers) == 1
    assert len(bangladesh_axis.containers) == 1
    assert len(nepal_axis.containers[0]) == 37
    assert len(bangladesh_axis.containers[0]) == 37
    assert [text.get_text() for text in figure.legends[0].get_texts()] == [
        NEPAL_LABEL,
        BANGLADESH_LABEL,
    ]
    assert nepal_axis.get_ylabel() == "人数（人）"
    assert bangladesh_axis.get_ylabel() == "人数（人）"
    assert nepal_axis.yaxis.label.get_color() == "#000000"
    assert bangladesh_axis.yaxis.label.get_color() == "#000000"
    assert nepal_axis.spines["top"].get_visible()
    assert nepal_axis.spines["bottom"].get_visible()
    assert nepal_axis.spines["left"].get_visible()
    assert bangladesh_axis.spines["right"].get_visible()
    assert any(
        text.get_text() == "数据来源：尼泊尔外国就业局、孟加拉国人力就业培训局"
        for text in figure.texts
    )
    assert _war_line_on(nepal_axis)


def _war_line_on(axis) -> bool:
    from matplotlib.colors import to_rgba

    from dashboard.analysis.uae.oil.charts import WAR_LINE_COLOR

    expected = to_rgba(WAR_LINE_COLOR)
    return any(
        tuple(to_rgba(line.get_color())) == expected
        and line.get_linestyle() == "--"
        for line in axis.get_lines()
    )


def test_chart_limits_dense_monthly_bars_to_the_latest_three_years() -> None:
    dates = pd.date_range("2020-01-31", periods=60, freq="ME")
    values = pd.DataFrame(
        {
            NEPAL_APPROVALS: range(1_000, 1_000 + len(dates)),
            BANGLADESH_CLEARANCES: range(2_000, 2_000 + len(dates)),
        },
        index=dates,
    )

    figure = build_foreign_labor_figure(
        values,
        title="劳工人数",
        source_text="测试来源",
    )

    assert [len(axis.containers[0]) for axis in figure.axes] == [37, 37]
