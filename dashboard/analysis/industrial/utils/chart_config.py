"""
Chart Configuration Utility
图表配置工具 - 统一的图表配置常量和函数

消除重复代码:
- 时间范围选项在多处重复定义
- 颜色方案在多处重复定义
- 图表布局配置在多处重复
"""

from typing import Dict, List, Tuple

# ==================== 常量定义 ====================

# 时间范围选项（全局统一）
TIME_RANGE_OPTIONS: List[str] = ["1年", "3年", "5年", "全部", "自定义"]

# 默认时间范围
DEFAULT_TIME_RANGE: str = "3年"

# 默认时间范围索引
DEFAULT_TIME_RANGE_INDEX: int = 1  # "3年"的索引

# 图表颜色方案（统一使用）
CHART_COLORS: List[str] = [
    '#1f77b4',  # 蓝色
    '#ff7f0e',  # 橙色
    '#2ca02c',  # 绿色
    '#d62728',  # 红色
    '#9467bd',  # 紫色
    '#8c564b',  # 棕色
    '#e377c2',  # 粉色
    '#7f7f7f',  # 灰色
    '#bcbd22',  # 黄绿色
    '#17becf'   # 青色
]

# 图表尺寸
CHART_HEIGHT_STANDARD: int = 600
CHART_HEIGHT_COMPACT: int = 500

# 图表边距
CHART_MARGIN_STANDARD: Dict[str, int] = {
    'l': 80,
    'r': 50,
    't': 30,
    'b': 120
}

CHART_MARGIN_WITH_LEGEND: Dict[str, int] = {
    'l': 80,
    'r': 50,
    't': 40,
    'b': 180
}

# 字体大小配置
FONT_SIZE_AXIS_TITLE: int = 16
FONT_SIZE_AXIS_TICK: int = 14
FONT_SIZE_LEGEND: int = 14

# 图例配置
LEGEND_CONFIG_BOTTOM_CENTER: Dict = {
    'orientation': "h",
    'yanchor': "top",
    'y': -0.18,
    'xanchor': "center",
    'x': 0.5,
    'font': dict(size=FONT_SIZE_LEGEND)
}

LEGEND_CONFIG_BOTTOM_CENTER_LARGE: Dict = {
    'orientation': "h",
    'yanchor': "top",
    'y': -0.30,
    'xanchor': "center",
    'x': 0.5,
    'font': dict(size=FONT_SIZE_LEGEND)
}

# 坐标轴配置
XAXIS_CONFIG_BASE: Dict = {
    'title': "",
    'type': "date",
    'showgrid': True,
    'gridwidth': 1,
    'gridcolor': 'lightgray',
}

YAXIS_CONFIG_BASE: Dict = {
    'title': "",
    'showgrid': True,
    'gridwidth': 1,
    'gridcolor': 'lightgray'
}

# 月份间隔配置
DTICK_3_MONTHS: str = "M3"
DTICK_6_MONTHS: str = "M6"
DTICK_12_MONTHS: str = "M12"


# ==================== 工具函数 ====================

def get_chart_color(index: int) -> str:
    """
    根据索引获取图表颜色

    Args:
        index: 颜色索引

    Returns:
        颜色代码（十六进制）
    """
    return CHART_COLORS[index % len(CHART_COLORS)]


def get_time_range_index(time_range: str) -> int:
    """
    获取时间范围选项的索引

    Args:
        time_range: 时间范围选项

    Returns:
        索引值，如果不存在返回默认索引
    """
    try:
        return TIME_RANGE_OPTIONS.index(time_range)
    except ValueError:
        return DEFAULT_TIME_RANGE_INDEX


def create_xaxis_config(
    dtick: str = DTICK_3_MONTHS,
    tickformat: str = "%Y-%m",
    min_date = None,
    max_date = None,
    tickangle: int = 0
) -> Dict:
    """
    创建X轴配置

    Args:
        dtick: 刻度间隔
        tickformat: 时间格式
        min_date: 最小日期
        max_date: 最大日期
        tickangle: 刻度角度

    Returns:
        X轴配置字典
    """
    config = XAXIS_CONFIG_BASE.copy()
    config['dtick'] = dtick
    config['tickformat'] = tickformat
    config['hoverformat'] = "%Y-%m"  # 修复hover显示：只显示年月
    config['tickfont'] = dict(size=FONT_SIZE_AXIS_TICK)
    config['title'] = dict(text="", font=dict(size=FONT_SIZE_AXIS_TITLE))

    if tickangle != 0:
        config['tickangle'] = tickangle

    if min_date and max_date:
        config['range'] = [min_date, max_date]

    return config


def create_yaxis_config(title: str = "") -> Dict:
    """
    创建Y轴配置

    Args:
        title: Y轴标题

    Returns:
        Y轴配置字典
    """
    config = YAXIS_CONFIG_BASE.copy()
    config['title'] = dict(text=title, font=dict(size=FONT_SIZE_AXIS_TITLE))
    config['tickfont'] = dict(size=FONT_SIZE_AXIS_TICK)
    return config


def create_standard_layout(
    title: str = "",
    height: int = CHART_HEIGHT_STANDARD,
    margin: Dict[str, int] = None,
    legend_config: Dict = None,
    barmode: str = None
) -> Dict:
    """
    创建标准图表布局配置

    Args:
        title: 图表标题
        height: 图表高度
        margin: 边距配置
        legend_config: 图例配置
        barmode: 条形图模式 ('stack', 'group', 'relative' 等)

    Returns:
        布局配置字典
    """
    layout = {
        'title': title,
        'height': height,
        'hovermode': 'x unified',
        'plot_bgcolor': 'white',
        'paper_bgcolor': 'white',
        'showlegend': True
    }

    if margin:
        layout['margin'] = margin
    else:
        layout['margin'] = CHART_MARGIN_STANDARD

    if legend_config:
        layout['legend'] = legend_config
    else:
        layout['legend'] = LEGEND_CONFIG_BOTTOM_CENTER

    if barmode:
        layout['barmode'] = barmode

    return layout


def get_opacity_by_index(index: int, base: float = 0.9, step: float = 0.15, min_opacity: float = 0.5) -> float:
    """
    根据索引计算透明度（用于堆叠图表）

    Args:
        index: 索引
        base: 基础透明度
        step: 递减步长
        min_opacity: 最小透明度

    Returns:
        透明度值
    """
    opacity = base - (index * step)
    return max(min_opacity, opacity)


def calculate_dtick_by_time_span(min_date, max_date, default: str = DTICK_6_MONTHS) -> str:
    """
    根据时间跨度计算合适的刻度间隔

    Args:
        min_date: 最小日期
        max_date: 最大日期
        default: 默认间隔

    Returns:
        刻度间隔字符串
    """
    if not min_date or not max_date:
        return default

    try:
        time_span_years = (max_date - min_date).days / 365.25

        if time_span_years <= 2:
            return DTICK_3_MONTHS  # 2年内：3个月间隔
        elif time_span_years <= 5:
            return DTICK_6_MONTHS  # 2-5年：6个月间隔
        else:
            return DTICK_12_MONTHS  # 5年以上：12个月间隔
    except Exception:
        return default
