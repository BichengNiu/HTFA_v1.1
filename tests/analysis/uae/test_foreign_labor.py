"""Tests for the foreign-labour companion chart."""

from io import BytesIO

import pandas as pd

from dashboard.analysis.uae.foreign_labor import (
    BANGLADESH_CLEARANCES,
    BANGLADESH_LABEL,
    FOREIGN_LABOR_SHEET,
    NEPAL_APPROVALS,
    NEPAL_LABEL,
    build_foreign_labor_figure,
    latest_common_month,
    load_foreign_labor_data,
)
from htfa.ui_shared.chart_legend import place_chart_legend_at_bottom


def _workbook_bytes(*, standard_protocol: bool = False) -> bytes:
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
            [
                "指标名称" if standard_protocol else "日期",
                NEPAL_APPROVALS,
                BANGLADESH_CLEARANCES,
            ],
            ["频率" if standard_protocol else "月", "月", "月"],
            ["单位" if standard_protocol else "日期", "人", "人"],
            ["来源" if standard_protocol else "各国官方劳工输出登记/部署/审批数据",
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


def test_loader_accepts_standard_workbook_protocol() -> None:
    data = load_foreign_labor_data(
        _workbook_bytes(standard_protocol=True),
        file_name="standard.xlsx",
    )

    assert data.values.columns.tolist() == [
        NEPAL_APPROVALS,
        BANGLADESH_CLEARANCES,
    ]


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
    # 模板（走 Ts plot_series 默认模板）：双轴图例为「变量名（左轴/右轴）」。
    legend = nepal_axis.get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == [
        f"{NEPAL_LABEL}（左轴）",
        f"{BANGLADESH_LABEL}（右轴）",
    ]
    assert nepal_axis.get_ylabel() == "万人"
    assert bangladesh_axis.get_ylabel() == "万人"
    # 双柱模板化：两根柱在同一时间点并排错开（x 起点不同），而不重叠。
    assert _bars_side_by_side(nepal_axis, bangladesh_axis)
    # 模板默认脊线：主轴保留下/左，右轴保留右，上脊线隐藏。
    assert not nepal_axis.spines["top"].get_visible()
    assert not bangladesh_axis.spines["top"].get_visible()
    assert bangladesh_axis.spines["right"].get_visible()
    assert any(
        text.get_text() == "数据来源：尼泊尔外国就业局、孟加拉国人力就业培训局"
        for text in figure.texts
    )
    # 战争起始基准线由模板 vlines 提供（参考线风格），并带红字战争标注。
    assert any("<-" in text.get_text() for text in nepal_axis.texts)


def _bars_side_by_side(left_axis, right_axis) -> bool:
    """双轴双柱：同一时间点上两根柱的 x 起点应错开（并排而非重叠）。"""
    left_x = [p.get_x() for p in left_axis.patches]
    right_x = [p.get_x() for p in right_axis.patches]
    if not left_x or not right_x:
        return False
    return any(l != r for l, r in zip(left_x, right_x))


def test_bottom_legend_keeps_both_dual_axis_bar_series() -> None:
    data = load_foreign_labor_data(_workbook_bytes(), file_name="test.xlsx")
    figure = build_foreign_labor_figure(
        data.values,
        title="鍔冲伐浜烘暟",
        source_text="娴嬭瘯鏉ユ簮",
    )

    place_chart_legend_at_bottom(figure)

    assert len(figure.legends) == 1
    assert [text.get_text() for text in figure.legends[0].get_texts()] == [
        f"{NEPAL_LABEL}（左轴）",
        f"{BANGLADESH_LABEL}（右轴）",
    ]


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
