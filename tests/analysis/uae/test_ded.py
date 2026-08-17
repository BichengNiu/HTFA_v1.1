"""Tests for the DED enterprise-registration / licence bar panel."""

from io import BytesIO

import matplotlib.colors
import pandas as pd
import pytest

from dashboard.analysis.uae.government_finance.ded import (
    DED_SERIES,
    ENTERPRISES_DISPLAY,
    ENTERPRISES_INDICATOR,
    LICENCES_DISPLAY,
    LICENCES_INDICATOR,
    build_ded_figure,
    load_ded_data,
)


def _workbook_bytes() -> bytes:
    """构造迷你月度_DED：企业数（单位家）+ 许可数（单位张），前六行元数据协议。"""

    dates = pd.date_range("2024-01-31", periods=14, freq="ME")
    enterprises = [800.0, 900.0, 1000.0, 1100.0, 1200.0, 1300.0, 1400.0,
                   1500.0, 1600.0, 1700.0, 1800.0, 1900.0, 2000.0, 2100.0]
    licences = [v * 3 for v in enterprises]
    metadata = pd.DataFrame(
        [
            ["DED", None, None, None],
            [
                "指标名称",
                ENTERPRISES_INDICATOR,
                LICENCES_INDICATOR,
                None,
            ],
            ["频率", "月", "月", "月"],
            ["单位", "家", "张", "张"],
            [
                "来源",
                "data.dubai Commerce Registry (commerce_number 按发照月去重)",
                "data.dubai Commerce Registry (main_license_number 按发照月去重)",
                "DET/迪拜媒体办新闻稿",
            ],
            ["更新时间", "2026-08-17", "2026-08-17", "2026-08-17"],
        ]
    )
    data = pd.DataFrame(
        {
            "日期": dates,
            ENTERPRISES_DISPLAY: enterprises,
            LICENCES_DISPLAY: licences,
        }
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
            sheet_name="月度_DED",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_ded_loader_reads_both_indicators_with_distinct_units() -> None:
    data = load_ded_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        ENTERPRISES_DISPLAY,
        LICENCES_DISPLAY,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-02-28")
    assert data.metadata[ENTERPRISES_DISPLAY].unit == "家"
    assert data.metadata[LICENCES_DISPLAY].unit == "张"
    assert data.metadata[ENTERPRISES_DISPLAY].source == "data.dubai Commerce Registry"


def test_ded_figure_renders_grouped_bars_and_matching_legend() -> None:
    data = load_ded_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_ded_figure(
        data.values,
        title="迪拜企业发证活动与新发执照",
        source_text="DED",
        last_month=pd.Period("2024-06", freq="M"),
    )

    axis = figure.axes[0]
    # 两条分组柱（BarContainer）
    assert len(axis.containers) == 2
    enterprise_bars = axis.containers[0].get_children()
    licence_bars = axis.containers[1].get_children()
    # 数轴上每个月份一对柱子（窗口 2022-06..2024-06 → 夹具中 2024-01..2024-06 共 6 个月）
    assert len(enterprise_bars) == 6
    assert len(licence_bars) == 6
    # 柱色与系列定义一致（黑/深蓝）
    assert enterprise_bars[0].get_facecolor()[:3] == pytest.approx(
        matplotlib.colors.to_rgb("#000000")
    )
    assert licence_bars[0].get_facecolor()[:3] == pytest.approx(
        matplotlib.colors.to_rgb("#1F4E79")
    )
    assert axis.get_ylabel() == "家 / 张"
    assert axis.get_ylim()[0] == 0
    # 图例与柱子对应：两个补丁句柄，颜色与柱色一致
    legend_handles = figure.legends[0].get_patches()
    assert len(legend_handles) == len(DED_SERIES)
    legend_texts = [t.get_text() for t in figure.legends[0].get_texts()]
    assert legend_texts == [ENTERPRISES_DISPLAY, LICENCES_DISPLAY]
    assert [h.get_facecolor()[:3] for h in legend_handles] == [
        matplotlib.colors.to_rgb("#000000"),
        matplotlib.colors.to_rgb("#1F4E79"),
    ]
    assert any(
        text.get_text() == "数据来源：DED" for text in figure.texts
    )
