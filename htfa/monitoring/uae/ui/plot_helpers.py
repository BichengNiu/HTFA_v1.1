from __future__ import annotations
import matplotlib
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import date2num
from matplotlib.figure import Figure
from matplotlib.transforms import blended_transform_factory
import numpy as np
from Ts.TsPlots.style import format_compact_y_axis as ts_format_compact_y_axis
from htfa.ui_shared.fonts import matplotlib_font_family

CHINESE_FONT_FAMILY = matplotlib_font_family()
WAR_START_DATE = pd.Timestamp("2026-03-01")
WAR_LINE_COLOR = "#C0392B"
_COUNT_AXIS_UNITS = ("个", "家", "张", "笔", "人", "人次", "艘次", "磅", "吨", "台")


def _count_axis_rules(unit: str) -> tuple[tuple[float, float, str], ...]:
    return (
        (10000000000.0, 10000000000.0, f"百亿{unit}"),
        (1000000000.0, 1000000000.0, f"十亿{unit}"),
        (100000000.0, 100000000.0, f"亿{unit}"),
        (10000000.0, 10000000.0, f"千万{unit}"),
        (1000.0, 10000.0, f"万{unit}"),
        (0.0, 1.0, unit),
    )


UAE_COMPACT_Y_AXIS_RULES = {
    "百万迪拉姆": ((100000.0, 1000000.0, "万亿迪拉姆"), (0.0, 100.0, "亿迪拉姆")),
    **{unit: _count_axis_rules(unit) for unit in _COUNT_AXIS_UNITS},
}


def create_report_axis() -> Axes:
    """Create an unregistered canvas that another Streamlit run cannot close."""
    figure = Figure(figsize=(9.4, 6.2))
    FigureCanvasAgg(figure)
    return figure.subplots()


def normalize_ts_axis(axis: Axes | np.ndarray) -> Axes:
    """返回 Ts plot_series 返回值中的第一个标量坐标轴。"""
    if isinstance(axis, Axes):
        return axis
    if isinstance(axis, np.ndarray):
        for candidate in axis.flat:
            if isinstance(candidate, Axes):
                return candidate
    raise TypeError("Ts plot_series did not return a Matplotlib Axes object")


def annotate_war(axis: Axes) -> None:
    """在战争时期的水平中间、图形上边框之上标注“<- 战争 ->”红色文字。"""
    x_max = axis.get_xlim()[1]
    if x_max < date2num(WAR_START_DATE):
        return
    axis.text(
        (date2num(WAR_START_DATE) + x_max) / 2,
        1.02,
        "<- 战争 ->",
        transform=blended_transform_factory(axis.transData, axis.transAxes),
        ha="center",
        va="bottom",
        color=WAR_LINE_COLOR,
        fontsize=9,
        fontfamily=CHINESE_FONT_FAMILY,
        clip_on=False,
        zorder=10,
    )


def apply_htfa_fonts(figure: Figure) -> None:
    """把 Ts 模板默认字体统一覆盖为当前平台可用的 CJK 字体。

    模板在 ``plot_series`` 内部通过 ``apply_fonts`` 配置 rcParams；本项目
    此函数在图完成后把坐标轴标题、刻度、
    轴内文字、图例与图注一并改为 ``CHINESE_FONT_FAMILY``。
    """
    matplotlib.rcParams["font.family"] = list(CHINESE_FONT_FAMILY)
    matplotlib.rcParams["font.sans-serif"] = list(CHINESE_FONT_FAMILY)
    matplotlib.rcParams["axes.unicode_minus"] = False
    for axis in figure.axes:
        format_compact_y_axis(axis)
        axis.title.set_fontfamily(CHINESE_FONT_FAMILY)
        axis.xaxis.label.set_fontfamily(CHINESE_FONT_FAMILY)
        axis.yaxis.label.set_fontfamily(CHINESE_FONT_FAMILY)
        for label in (*axis.get_xticklabels(), *axis.get_yticklabels()):
            label.set_fontfamily(CHINESE_FONT_FAMILY)
        for text in axis.texts:
            text.set_fontfamily(CHINESE_FONT_FAMILY)
    for legend in figure.legends:
        for text in legend.get_texts():
            text.set_fontfamily(CHINESE_FONT_FAMILY)
        legend_title = legend.get_title()
        if legend_title.get_text():
            legend_title.set_fontfamily(CHINESE_FONT_FAMILY)
    for text in figure.texts:
        text.set_fontfamily(CHINESE_FONT_FAMILY)


def format_compact_y_axis(axis: Axes) -> None:
    """用 TsPlots 的通用规则引擎压缩 UAE 纵轴刻度。"""
    ts_format_compact_y_axis(
        axis, unit=axis.get_ylabel().strip(), rules=UAE_COMPACT_Y_AXIS_RULES
    )
