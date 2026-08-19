"""Tests for the DED enterprise-registration / licence bar panel."""

from io import BytesIO

import matplotlib.colors
import pandas as pd
import pytest

from dashboard.analysis.uae.government_finance.ded import (
    ENTERPRISES_DISPLAY,
    ENTERPRISES_INDICATOR,
    LICENCES_DISPLAY,
    LICENCES_INDICATOR,
    build_ded_figure,
    load_ded_data,
)
from Ts.TsPlots.style import GRAY


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


def test_ded_figure_renders_single_licence_bar_without_legend() -> None:
    data = load_ded_data(_workbook_bytes(), file_name="test.xlsx")

    figure = build_ded_figure(
        data.values,
        title="迪拜新发执照数",
        source_text="DED",
        last_month=pd.Period("2024-06", freq="M"),
    )

    axis = figure.axes[0]
    # 只画当月新发执照数一条柱（BarContainer）
    assert len(axis.containers) == 1
    licence_bars = axis.containers[0].get_children()
    # 窗口 2022-06..2024-06 → 夹具中 2024-01..2024-06 共 6 个月
    assert len(licence_bars) == 6
    # 柱色统一为灰色（bar_face_color 覆盖模板首色）
    assert licence_bars[0].get_facecolor()[:3] == pytest.approx(
        matplotlib.colors.to_rgb(GRAY)
    )
    assert axis.get_ylabel() == "张"
    assert axis.get_ylim()[0] == 0
    # 单序列图默认不显示图例（模板规则：len(series)==1 且未显式 legend_labels）。
    assert axis.get_legend() is None
    assert any(
        text.get_text() == "数据来源：DED" for text in figure.texts
    )
