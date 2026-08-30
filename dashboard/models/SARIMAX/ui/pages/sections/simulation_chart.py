"""SARIMAX 模拟比较图的 Streamlit 渲染适配器。

模拟路径和统计量由核心计算模块生成；本模块只负责把稳定的比较结果
转换为图形并交给 HTFA 的统一渲染器。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.models.SARIMAX.core.modeling import translate_ts_error
from dashboard.models.SARIMAX.core.simulation import SARIMAXSimulationComparison

logger = logging.getLogger(__name__)


def render_sarimax_simulation_chart(
    st_obj: Any,
    comparison: SARIMAXSimulationComparison,
) -> None:
    """用 TsPlots 风格渲染模拟路径区间和 ACF 区间。

    Parameters
    ----------
    st_obj : object
        提供 ``warning`` 方法的 Streamlit 页面对象。
    comparison : SARIMAXSimulationComparison
        核心模拟模块生成的实际序列与模拟路径比较结果。
    """
    try:
        with matplotlib_date_compatibility():
            figure, _ = _plot_sarimax_simulation_comparison(comparison)
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:  # noqa: BLE001 - 图形渲染边界
        st_obj.warning(f"模拟路径比较无法绘制：{translate_ts_error(exc)}")
        logger.warning("SARIMAX 模拟路径比较绘制失败", exc_info=True)


def _plot_sarimax_simulation_comparison(
    comparison: SARIMAXSimulationComparison,
) -> tuple[Any, tuple[Any, Any]]:
    """构造模拟路径比较图，不处理 Streamlit 页面状态。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from Ts.TsPlots import plot_series
    from Ts.TsPlots.style import (
        AXIS_LABEL_FONTSIZE,
        BAND_ALPHA,
        BAND_COLOR,
        BLACK,
        DARK_BLUE,
        REFERENCE_LINE_STYLE,
        REFERENCE_LINE_WIDTH,
        TIGHT_PAD,
        ZERO_LINE_COLOR,
        _ensure_fonts,
        style_axes,
    )

    _ensure_fonts()
    figure, axes = plt.subplots(
        2,
        1,
        figsize=(12, 8),
        gridspec_kw={"height_ratios": (3, 1)},
    )
    time_axis, acf_axis = axes
    frame = pd.DataFrame(
        {
            "实际序列": comparison.actual,
            "模拟中位数": comparison.simulated_median,
        },
        index=comparison.index,
    )
    plot_series(
        frame,
        ax=time_axis,
        title="实际序列与模拟路径分布",
        xtitle="",
        ytitle="",
        linewidth=2.0,
        markersize=0,
        show_legend=True,
        legend_loc="upper left",
        facet=False,
        auto_dual_y=False,
        grid=False,
    )
    time_axis.fill_between(
        comparison.index,
        comparison.simulated_lower,
        comparison.simulated_upper,
        color=BAND_COLOR,
        alpha=BAND_ALPHA,
        linewidth=0,
        zorder=0,
    )
    handles = list(time_axis.lines)
    labels = [line.get_label() for line in time_axis.lines]
    handles.append(
        Patch(
            facecolor=BAND_COLOR,
            edgecolor="none",
            alpha=BAND_ALPHA,
        )
    )
    labels.append(f"模拟{comparison.confidence_level:.0%}区间")
    time_axis.legend(handles, labels, frameon=False)

    lags = np.arange(1, comparison.acf_lags + 1)
    acf_axis.fill_between(
        lags,
        comparison.simulated_acf_lower,
        comparison.simulated_acf_upper,
        color=BAND_COLOR,
        alpha=BAND_ALPHA,
        linewidth=0,
        zorder=0,
    )
    acf_axis.plot(
        lags,
        comparison.actual_acf,
        color=BLACK,
        linewidth=2.0,
        marker="o",
        markersize=4,
        label="实际 ACF",
        zorder=3,
    )
    acf_axis.plot(
        lags,
        comparison.simulated_acf_median,
        color=DARK_BLUE,
        linewidth=2.0,
        marker="s",
        markersize=4,
        label="模拟 ACF 中位数",
        zorder=3,
    )
    acf_axis.axhline(
        0.0,
        color=ZERO_LINE_COLOR,
        linestyle=REFERENCE_LINE_STYLE,
        linewidth=REFERENCE_LINE_WIDTH,
        zorder=2,
    )
    acf_axis.set_title(
        f"ACF 比较（滞后 1–{comparison.acf_lags}）",
        fontsize=AXIS_LABEL_FONTSIZE,
        fontweight="normal",
        pad=6,
    )
    acf_axis.set_xlabel("滞后期数", fontsize=AXIS_LABEL_FONTSIZE)
    acf_axis.set_ylabel("ACF值", fontsize=AXIS_LABEL_FONTSIZE)
    acf_axis.set_xticks(lags)
    style_axes(acf_axis, grid=False)
    figure.tight_layout(pad=TIGHT_PAD)
    return figure, (time_axis, acf_axis)


__all__ = ["render_sarimax_simulation_chart"]
