"""数据概览的常量与中文→枚举映射（纯数据，无 streamlit 依赖）。"""

from __future__ import annotations

# 预览图可调参数范围（与 TsPlots.plot_series 参数对应）。
LINE_WIDTH_RANGE = (0.5, 4.0)
MARKER_SIZE_RANGE = (0, 12)
MARKER_EDGE_RANGE = (0.0, 4.0)
LEGEND_LOCATIONS = (
    "best",
    "upper right",
    "upper left",
    "lower left",
    "lower right",
)
TITLE_POSITIONS = ("左上", "上居中", "右上", "下居中")
TITLE_POSITION_MAP = {
    "左上": ("left", "top"),
    "上居中": ("center", "top"),
    "右上": ("right", "top"),
    "下居中": ("center", "bottom"),
}
XTITLE_LOCATIONS = ("左", "中", "右")
XTITLE_LOCATION_MAP = {"左": "left", "中": "center", "右": "right"}
NOTE_LOCATIONS = ("左", "中", "右")
NOTE_LOCATION_MAP = {"左": "left", "中": "center", "右": "right"}
YTITLE_POSITIONS = ("置顶", "侧边")
YTITLE_POSITION_MAP = {"置顶": "top", "侧边": "side"}
FREQUENCIES = ("自动", "day", "week", "month", "quarter", "year")
REFERENCE_LINE_STYLES = ("--", "-", ":", "-.")
GRID_STYLES = ("不显示", "纵网格", "横网格", "纵横网格")
GRID_STYLE_MAP = {
    "不显示": (False, "both"),
    "纵网格": (True, "x"),
    "横网格": (True, "y"),
    "纵横网格": (True, "both"),
}
GRID_LINESTYLES = ("--", "-", ":", "-.")
GRID_WIDTH_RANGE = (0.2, 3.0)
COLOR_NAMES = ("红", "橙", "黄", "绿", "蓝", "紫", "灰")
COLOR_HEX_MAP = {
    "红": "#d9534f",
    "橙": "#e67e22",
    "黄": "#f1c40f",
    "绿": "#2ecc71",
    "蓝": "#3498db",
    "紫": "#9b59b6",
    "灰": "#999999",
}
ASPECT_RATIOS = ("自定义", "16:9", "4:3", "3:2", "1:1")
ASPECT_RATIO_MAP = {"16:9": 16 / 9, "4:3": 4 / 3, "3:2": 3 / 2, "1:1": 1.0}

# 数据表高级选项：数值筛选运算符（显示文本 -> pandas 比较方法）。
FILTER_OPERATORS = {
    "≥": "ge",
    "≤": "le",
    ">": "gt",
    "<": "lt",
    "=": "eq",
}

# 时间筛选预设（按数据频率），value 为最近期数（"custom" 为自定义）。
TIME_PRESETS = {
    "year": [
        ("全部", "all"),
        ("过去1年", "1"),
        ("过去3年", "3"),
        ("过去5年", "5"),
        ("自定义", "custom"),
    ],
    "quarter": [
        ("全部", "all"),
        ("过去1季度", "1"),
        ("过去2季度", "2"),
        ("过去4季度", "4"),
        ("自定义", "custom"),
    ],
    "month": [
        ("全部", "all"),
        ("过去1个月", "1"),
        ("过去3个月", "3"),
        ("过去6个月", "6"),
        ("过去12个月", "12"),
        ("自定义", "custom"),
    ],
    "week": [
        ("全部", "all"),
        ("过去1周", "1"),
        ("过去4周", "4"),
        ("过去12周", "12"),
        ("过去52周", "52"),
        ("自定义", "custom"),
    ],
    "day": [
        ("全部", "all"),
        ("过去7天", "7"),
        ("过去30天", "30"),
        ("过去90天", "90"),
        ("过去365天", "365"),
        ("自定义", "custom"),
    ],
}
# 频率 -> 自定义起止的 Period 频率（年/季/月；周与日走日期控件）。
FREQ_PERIOD = {"year": "Y", "quarter": "Q", "month": "M"}

# 预览表格默认显示行数。
PREVIEW_TABLE_ROWS = 10
# 图形纵横比 16:9 宽幅：点右上角放大（全屏展开）时图表能自适应整个
# 页面；dpi=200 保证放大后仍清晰。普通视图下图形在 5/9 图列内拉伸，
# 宽幅渲染高度与 10 行表格高度接近。
PREVIEW_FIGSIZE = (12.8, 7.2)
PREVIEW_DPI = 200


__all__ = [
    "ASPECT_RATIO_MAP",
    "ASPECT_RATIOS",
    "COLOR_HEX_MAP",
    "COLOR_NAMES",
    "FILTER_OPERATORS",
    "FREQ_PERIOD",
    "FREQUENCIES",
    "GRID_LINESTYLES",
    "GRID_STYLE_MAP",
    "GRID_STYLES",
    "GRID_WIDTH_RANGE",
    "LEGEND_LOCATIONS",
    "LINE_WIDTH_RANGE",
    "MARKER_EDGE_RANGE",
    "MARKER_SIZE_RANGE",
    "NOTE_LOCATION_MAP",
    "NOTE_LOCATIONS",
    "PREVIEW_DPI",
    "PREVIEW_FIGSIZE",
    "PREVIEW_TABLE_ROWS",
    "REFERENCE_LINE_STYLES",
    "TIME_PRESETS",
    "TITLE_POSITION_MAP",
    "TITLE_POSITIONS",
    "XTITLE_LOCATION_MAP",
    "XTITLE_LOCATIONS",
    "YTITLE_POSITION_MAP",
    "YTITLE_POSITIONS",
]
