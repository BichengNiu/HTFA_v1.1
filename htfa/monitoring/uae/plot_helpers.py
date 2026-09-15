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
from Ts.TsPlots.style import format_compact_y_axis as ts_format_compact_y_axis


CHINESE_FONT_FAMILY = ["Microsoft YaHei", "SimHei"]
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
    "OPEC MOMR": "欧佩克月度石油市场报告",
    "OPEC MOMR（secondary sources）": "欧佩克月度石油市场报告",
    "Wind": "万得",
    "EIA": "美国能源信息署",
    "U.S. EIA": "美国能源信息署（EIA）",
    "IMF Primary Commodity Price System (PCPS)": "国际货币基金组织初级商品价格体系（PCPS）",
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
    "UAE_COMPACT_Y_AXIS_RULES",
    "WAR_LINE_COLOR",
    "WAR_START_DATE",
    "annotate_war",
    "apply_htfa_fonts",
    "format_compact_y_axis",
    "normalize_ts_axis",
    "source_note",
    "translate_source_text",
]
