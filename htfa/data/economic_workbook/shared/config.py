"""多频率数据预览的共享配置。"""

from ..core.base_config import FrequencyConfig


FREQUENCY_CONFIGS = {
    "weekly": FrequencyConfig(
        english_name="weekly",
        display_name="周度",
        sort_column="环比上周",
        highlight_columns=["环比上周"],
        percentage_columns=["环比上周"],
        indicator_name_column="周度指标名称",
        date_column="最新日期",
        column_order=["周度指标名称", "最新日期", "最新值", "上周值", "环比上周"],
        color="#1f77b4",
    ),
    "monthly": FrequencyConfig(
        english_name="monthly",
        display_name="月度",
        sort_column="环比上月",
        highlight_columns=["环比上月", "同比上年"],
        percentage_columns=["环比上月", "同比上年"],
        indicator_name_column="月度指标名称",
        date_column="最新月份",
        column_order=[
            "月度指标名称", "最新月份", "最新值", "上月值", "环比上月", "同比上年"
        ],
        color="#ff7f0e",
    ),
    "daily": FrequencyConfig(
        english_name="daily",
        display_name="日度",
        sort_column="环比昨日",
        highlight_columns=["环比昨日", "同比上年"],
        percentage_columns=["环比昨日", "环比上周", "环比上月", "同比上年"],
        indicator_name_column="日度指标名称",
        date_column="最新日期",
        column_order=[
            "日度指标名称", "最新日期", "最新值", "昨日值", "环比昨日", "上周均值", "上月均值"
        ],
        color="#2ca02c",
    ),
    "ten_day": FrequencyConfig(
        english_name="ten_day",
        display_name="旬度",
        sort_column="环比上旬",
        highlight_columns=["环比上旬"],
        percentage_columns=["环比上旬"],
        indicator_name_column="旬度指标名称",
        date_column="最新日期",
        column_order=["旬度指标名称", "最新日期", "最新值", "上旬值", "环比上旬"],
        color="#d62728",
    ),
    "yearly": FrequencyConfig(
        english_name="yearly",
        display_name="年度",
        sort_column="同比上年",
        highlight_columns=["同比上年"],
        percentage_columns=["同比上年"],
        indicator_name_column="年度指标名称",
        date_column="最新年份",
        column_order=[
            "年度指标名称", "最新年份", "最新值", "上年值", "同比上年", "两年前值", "三年前值"
        ],
        color="#9467bd",
    ),
    "quarterly": FrequencyConfig(
        english_name="quarterly",
        display_name="季度",
        sort_column="环比上季",
        highlight_columns=["环比上季", "同比上年"],
        percentage_columns=["环比上季", "同比上年"],
        indicator_name_column="季度指标名称",
        date_column="最新季度",
        column_order=[
            "季度指标名称", "最新季度", "最新值", "上季值", "环比上季", "上年同季值", "同比上年"
        ],
        color="#8c564b",
    ),
}

COLORS = {
    "current_year": "red",
    "previous_year": "blue",
    "historical_mean": "grey",
    "historical_range": "rgba(211, 211, 211, 0.5)",
    "positive": "#ffcdd2",
    "negative": "#c8e6c9",
}

UI_TEXT = {
    "select_industry": "选择行业大类",
    "select_type": "选择指标类型",
    "all_option": "全部",
    "download_label": "下载数据摘要 (CSV)",
    "no_data_warning": "筛选条件 \"{}\" 没有匹配的指标。",
    "loading_message": "正在生成 {} 的图表...",
    "empty_data": "暂无{}数据。",
}

_COMMON_LAYOUT = {
    "margin": {"l": 50, "r": 30, "t": 60, "b": 120},
    "legend": {
        "orientation": "h",
        "yanchor": "bottom",
        "y": -0.3,
        "xanchor": "center",
        "x": 0.5,
    },
}

PLOT_CONFIGS = {
    "weekly": {
        "x_range": range(1, 54),
        "x_label_func": lambda value: f"W{value}",
        "x_tick_interval": 4,
        "historical_years": 5,
        "layout": _COMMON_LAYOUT,
    },
    "monthly": {
        "x_range": range(1, 13),
        "x_label_func": lambda value: f"{value}月",
        "x_tick_interval": 1,
        "historical_years": 5,
        "layout": _COMMON_LAYOUT,
    },
    "daily": {
        "x_range": range(1, 367),
        "x_label_func": lambda value: f"{value}日",
        "x_tick_vals": [1, 32, 61, 92, 122, 153, 183, 214, 245, 275, 306, 336],
        "x_tick_labels": [
            "1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月",
        ],
        "historical_years": 5,
        "layout": _COMMON_LAYOUT,
    },
    "ten_day": {
        "x_range": range(1, 37),
        "x_label_func": lambda value: f"第{value}旬",
        "x_tick_vals": [value - 0.5 for value in range(1, 38, 3)],
        "x_tick_labels": [f"{value}月" for value in range(1, 13)] + [""],
        "historical_years": 5,
        "layout": _COMMON_LAYOUT,
    },
    "yearly": {
        "layout": {"margin": {"l": 50, "r": 30, "t": 60, "b": 100}},
    },
    "quarterly": {
        "x_range": range(1, 5),
        "x_label_func": lambda value: f"Q{value}",
        "x_tick_interval": 1,
        "historical_years": 5,
        "layout": _COMMON_LAYOUT,
    },
}
