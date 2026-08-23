"""阿联酋监测模块共享的 Matplotlib 绘图基础设施。

石油、外籍劳动力、政府财政等面板共用同一套双轴图布局、
月份刻度、来源注释与中文字体设置。
"""

from __future__ import annotations

import re

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.dates import date2num
from matplotlib.figure import Figure
from matplotlib.transforms import blended_transform_factory
import numpy as np
from Ts.TsPlots.style import (
    apply_fonts,
    format_compact_y_axis as ts_format_compact_y_axis,
)


CHINESE_FONT_FAMILY = ["Microsoft YaHei", "SimHei"]
SOURCE_NOTE_Y = 0.025
WAR_START_DATE = pd.Timestamp("2026-03-01")
WAR_LINE_COLOR = "#C0392B"

_COUNT_AXIS_UNITS = (
    "个",
    "家",
    "张",
    "笔",
    "人",
    "人次",
    "艘次",
    "磅",
    "吨",
    "台",
)


def _count_axis_rules(unit: str) -> tuple[tuple[float, float, str], ...]:
    return (
        (10_000_000_000.0, 10_000_000_000.0, f"百亿{unit}"),
        (1_000_000_000.0, 1_000_000_000.0, f"十亿{unit}"),
        (100_000_000.0, 100_000_000.0, f"亿{unit}"),
        (10_000_000.0, 10_000_000.0, f"千万{unit}"),
        (1_000.0, 10_000.0, f"万{unit}"),
        (0.0, 1.0, unit),
    )


UAE_COMPACT_Y_AXIS_RULES = {
    "百万迪拉姆": (
        (100_000.0, 1_000_000.0, "万亿迪拉姆"),
        (0.0, 100.0, "亿迪拉姆"),
    ),
    **{
        unit: _count_axis_rules(unit)
        for unit in _COUNT_AXIS_UNITS
    },
}

SOURCE_DISPLAY_NAMES = {
    "ICE": "洲际交易所",
    "OPEC": "欧佩克",
    "Wind": "万得",
    "EIA": "美国能源信息署",
    "Baker Hughes": "贝克休斯",
    "CBUAE": "阿联酋央行",
    "CBUAE QER": "阿联酋央行季度经济报告",
    "UAE Ministry of Finance (MOF GFS)": "阿联酋财政部（政府财政统计）",
    "DLD": "迪拜土地局",
    "DED": "迪拜经济局",
    "S&P Global": "标普全球",
    "S&P Global / Trading Economics（公开样本）": "标普全球/全球经济数据平台（公开样本）",
    "Nepal DoFE": "尼泊尔外国就业局",
    "尼泊尔 DoFE monthly final labour approval": "尼泊尔外国就业局",
    "Bangladesh BMET": "孟加拉国人力就业培训局",
    "孟加拉国 BMET/OEP Country Clearance": "孟加拉国人力就业培训局",
    "菲律宾 DMW Monthly Compendium Tab 11": "菲律宾移民工人部月度汇编表 11",
    "UN Comtrade": "联合国商品贸易统计数据库",
    "MEsteel（CFR/CPT UAE）": "MEsteel 钢材数据（CFR/CPT 阿联酋）",
    "IMF PortWatch (HDX mirror)": "国际货币基金组织港口监测（HDX 镜像）",
    "Emirates Post (bayanat.ae)": "阿联酋邮政（bayanat.ae）",
    "SCAD": "沙迦统计与社区发展局",
    "TDRA Open Data": "电信和数字政府监管局开放数据",
    "RTA Open Data (Data Dubai)": "迪拜道路与交通管理局开放数据（迪拜数据）",
    "Cloudflare Radar (UAE)": "Cloudflare 雷达（阿联酋）",
    "WAM / UAE official source registry": "WAM/阿联酋官方来源登记表",
    "US DOT BTS T-100 International Segment (All Carriers)": "美国交通部统计局 BTS T-100 国际航段（全部承运人）",
    "Salik (salik.ae IR)": "Salik 道路收费系统（salik.ae 投资者关系）",
    "Google Trends/工作搜索热度 CSV": "谷歌趋势/工作搜索热度 CSV",
    "Google Trends": "谷歌趋势",
    "Google 趋势": "谷歌趋势",
    "Eurostat avia_paexcc/avia_goexcc（EU27_2020→AE，官方 API）": "欧盟统计局 avia_paexcc/avia_goexcc（EU27_2020→阿联酋，官方 API）",
    "Dubai Customs Airway Bill Details": "迪拜海关航空运单明细",
    "Dubai Customs Airway Bill Details（data.dubai 开放数据，ID 459114）": "迪拜海关航空运单明细（data.dubai 开放数据，ID 459114）",
    "Dubai Land Department": "迪拜土地局",
    "Dubai Land Department (Mo'asher)": "迪拜土地局（Mo'asher）",
    "DET/迪拜媒体办新闻稿": "迪拜经济与旅游部/迪拜媒体办公室新闻稿",
    "data.dubai Commerce Registry": "data.dubai 商业登记库",
    "data.dubai Commerce Registry (commerce_number 按发照月去重)": "data.dubai 商业登记库（commerce_number 按发照月去重）",
    "data.dubai Commerce Registry (main_license_number 按发照月去重)": "data.dubai 商业登记库（main_license_number 按发照月去重）",
    "data.dubai Commerce Registry 原始快照": "data.dubai 商业登记库原始快照",
    "UN Comtrade (HS87 镜像为主)": "联合国商品贸易统计数据库（HS87 以镜像为主）",
    "UN Comtrade (HS87 镜像口径)": "联合国商品贸易统计数据库（HS87 镜像口径）",
}


def normalize_ts_axis(axis: Axes | np.ndarray) -> Axes:
    """返回 Ts plot_series 返回值中的第一个标量坐标轴。"""

    if isinstance(axis, Axes):
        return axis
    if isinstance(axis, np.ndarray):
        for candidate in axis.flat:
            if isinstance(candidate, Axes):
                return candidate
    raise TypeError("Ts plot_series did not return a Matplotlib Axes object")


def new_ts_figure_axis() -> tuple[Figure, Axes]:
    """创建标量坐标轴，避免 Ts 拆分多序列图表。"""

    apply_fonts()
    figure = Figure(figsize=(9.4, 6.2), dpi=120)
    return figure, figure.add_subplot(111)


def translate_source_text(source_text: str) -> str:
    """把来源字符串中的数据源名称统一转换为中文展示文本。"""

    names = [
        _remove_parenthetical_text(
            SOURCE_DISPLAY_NAMES.get(part.strip(), part.strip())
        )
        for part in re.split(r"[、；]", source_text)
        if part.strip()
    ]
    return "、".join(names)


def _remove_parenthetical_text(value: str) -> str:
    """删除来源展示名中的中英文括号及括号内说明。"""

    cleaned = value
    while True:
        without_parenthetical = re.sub(
            r"\s*(?:（[^（）]*）|\([^()]*\))",
            "",
            cleaned,
        )
        if without_parenthetical == cleaned:
            return cleaned.strip()
        cleaned = without_parenthetical


def source_note(source_text: str) -> str:
    """把原始来源字符串转换为中文图注。"""

    return f"数据来源：{translate_source_text(source_text)}"


def add_source_note(figure: Figure, source_text: str) -> None:
    """把来源统一放在图形左下角边距内（字号对齐模板 NOTE_FONTSIZE）。"""

    figure.text(
        0.04,
        SOURCE_NOTE_Y,
        source_note(source_text),
        ha="left",
        va="bottom",
        fontsize=14,
        color="#222222",
        fontfamily=CHINESE_FONT_FAMILY,
        clip_on=False,
    )


def _add_war_line(axis: Axes) -> None:
    """2026 年 3 月美伊战争起始位置绘制红色虚线竖线。"""

    if axis.get_xlim()[1] < date2num(WAR_START_DATE):
        return
    axis.axvline(
        date2num(WAR_START_DATE),
        color=WAR_LINE_COLOR,
        linewidth=1.5,
        linestyle="--",
        zorder=5,
    )


def add_bottom_legend(
    figure: Figure,
    handles,
    labels,
    *,
    ncol: int,
    y: float = 0.115,
) -> None:
    """在图形底部添加统一的水平图例（字号对齐模板 LEGEND_FONTSIZE）。

    仅手动绘制的图表（如外籍劳动力双柱图）使用；走模板的图表由
    ``plot_series`` 的 ``BottomLegend`` 托管。
    """

    figure.legend(
        handles=handles,
        labels=labels,
        loc="lower center",
        bbox_to_anchor=(0.5, y),
        frameon=False,
        prop={"family": CHINESE_FONT_FAMILY[0], "size": 15},
        ncol=ncol,
    )


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


def apply_strict_month_ticks(
    axis: Axes,
    index: pd.Index,
) -> None:
    """绘制月份刻度和年度范围线，只包含真实数据月份。"""

    periods = (
        pd.PeriodIndex(pd.DatetimeIndex(index), freq="M")
        .unique()
        .sort_values()
    )
    if periods.empty:
        return
    tick_periods = periods[periods.month % 3 == 0]
    tick_dates = tick_periods.to_timestamp(how="end").normalize()
    axis.set_xticks(tick_dates)
    axis.set_xticklabels(
        [f"{period.month}月" for period in tick_periods],
        rotation=0,
        ha="center",
        fontsize=9,
    )
    axis.tick_params(axis="x", pad=5)

    year_line_y = -0.18
    cap_height = 0.018
    xaxis_transform = axis.get_xaxis_transform()
    for year in periods.year.unique():
        year_periods = periods[periods.year == year]
        start_date = year_periods[0].to_timestamp(how="end").normalize()
        end_date = year_periods[-1].to_timestamp(how="end").normalize()
        middle_date = start_date + (end_date - start_date) / 2
        axis.hlines(
            year_line_y,
            start_date,
            end_date,
            color="#555555",
            linewidth=0.8,
            transform=xaxis_transform,
            clip_on=False,
        )
        axis.vlines(
            [start_date, end_date],
            year_line_y - cap_height,
            year_line_y + cap_height,
            color="#555555",
            linewidth=0.8,
            transform=xaxis_transform,
            clip_on=False,
        )
        axis.text(
            middle_date,
            year_line_y,
            f" {year}年 ",
            ha="center",
            va="center",
            fontsize=9,
            color="#333333",
            fontfamily=CHINESE_FONT_FAMILY,
            backgroundcolor="white",
            transform=xaxis_transform,
            clip_on=False,
        )
    first_date = periods[0].to_timestamp(how="start").normalize()
    last_date = periods[-1].to_timestamp(how="end").normalize()
    axis.set_xlim(
        first_date - pd.Timedelta(days=10),
        last_date + pd.Timedelta(days=10),
    )
    _add_war_line(axis)


def finish_dual_axis_figure(
    figure: Figure,
    *,
    top: float,
    right: float = 0.895,
) -> None:
    """统一双轴图在 Streamlit 双栏中的尺寸和留白。"""

    figure.set_size_inches(9.4, 6.2, forward=True)
    figure.subplots_adjust(
        left=0.105,
        right=right,
        bottom=0.30,
        top=top,
    )
    apply_htfa_fonts(figure)


def apply_htfa_fonts(figure: Figure) -> None:
    """把 Ts 模板默认字体（Times New Roman + 仿宋）统一覆盖为微软雅黑。

    模板在 ``plot_series`` 内部通过 ``apply_fonts`` 配置 rcParams；本项目
    豁免项要求全图使用微软雅黑，此函数在图完成后把坐标轴标题、刻度、
    轴内文字、图例与图注一并改为 ``CHINESE_FONT_FAMILY``。
    """

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
        axis,
        unit=axis.get_ylabel().strip(),
        rules=UAE_COMPACT_Y_AXIS_RULES,
    )


__all__ = [
    "CHINESE_FONT_FAMILY",
    "SOURCE_DISPLAY_NAMES",
    "SOURCE_NOTE_Y",
    "UAE_COMPACT_Y_AXIS_RULES",
    "WAR_LINE_COLOR",
    "WAR_START_DATE",
    "add_source_note",
    "annotate_war",
    "apply_htfa_fonts",
    "apply_strict_month_ticks",
    "finish_dual_axis_figure",
    "format_compact_y_axis",
    "new_ts_figure_axis",
    "normalize_ts_axis",
    "source_note",
    "translate_source_text",
]
