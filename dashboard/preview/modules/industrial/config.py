"""
工业数据预览配置

从原config.py迁移的工业特定配置
"""

from typing import List, Dict, Any
from dashboard.preview.core.base_config import BasePreviewConfig, FrequencyConfig


class IndustrialConfig(BasePreviewConfig):
    """工业数据预览配置

    实现工业子模块的具体配置
    """

    def __init__(self):
        """初始化工业配置"""
        self._frequencies = ['weekly', 'monthly', 'daily', 'ten_day', 'quarterly', 'yearly']
        self._frequency_configs = self._build_frequency_configs()
        self._colors = self._build_colors()
        self._ui_text = self._build_ui_text()
        self._plot_config = self._build_plot_config()
        self._summary_config = self._build_summary_config()

    def get_frequencies(self) -> List[str]:
        """返回支持的频率列表"""
        return self._frequencies

    def get_frequency_config(self, freq: str) -> FrequencyConfig:
        """获取指定频率的配置"""
        return self._frequency_configs.get(freq)

    def get_colors(self) -> Dict[str, str]:
        """获取颜色配置"""
        return self._colors

    def get_ui_text(self) -> Dict[str, str]:
        """获取UI文本配置"""
        return self._ui_text

    def get_plot_config(self) -> Dict[str, Any]:
        """获取绘图配置"""
        return self._plot_config

    def get_summary_config(self) -> Dict[str, Any]:
        """获取摘要配置"""
        return self._summary_config

    def _build_frequency_configs(self) -> Dict[str, FrequencyConfig]:
        """构建频率配置"""
        return {
            'weekly': FrequencyConfig(
                english_name='weekly',
                display_name='周度',
                sort_column='环比上周',
                highlight_columns=['环比上周'],
                percentage_columns=['环比上周'],
                indicator_name_column='周度指标名称',
                date_column='最新日期',
                column_order=[
                    '周度指标名称', '最新日期', '最新值', '上周值',
                    '环比上周'
                ],
                color='#1f77b4'
            ),
            'monthly': FrequencyConfig(
                english_name='monthly',
                display_name='月度',
                sort_column='环比上月',
                highlight_columns=['环比上月', '同比上年'],
                percentage_columns=['环比上月', '同比上年'],
                indicator_name_column='月度指标名称',
                date_column='最新月份',
                column_order=[
                    '月度指标名称', '最新月份', '最新值', '上月值',
                    '环比上月', '同比上年'
                ],
                color='#ff7f0e'
            ),
            'daily': FrequencyConfig(
                english_name='daily',
                display_name='日度',
                sort_column='环比昨日',
                highlight_columns=['环比昨日', '同比上年'],
                percentage_columns=['环比昨日', '环比上周', '环比上月', '同比上年'],
                indicator_name_column='日度指标名称',
                date_column='最新日期',
                column_order=[
                    '日度指标名称', '最新日期', '最新值',
                    '昨日值', '环比昨日',
                    '上周均值', '上月均值'
                ],
                color='#2ca02c'
            ),
            'ten_day': FrequencyConfig(
                english_name='ten_day',
                display_name='旬度',
                sort_column='环比上旬',
                highlight_columns=['环比上旬'],
                percentage_columns=['环比上旬'],
                indicator_name_column='旬度指标名称',
                date_column='最新日期',
                column_order=[
                    '旬度指标名称', '最新日期', '最新值',
                    '上旬值', '环比上旬'
                ],
                color='#d62728'
            ),
            'yearly': FrequencyConfig(
                english_name='yearly',
                display_name='年度',
                sort_column='同比上年',
                highlight_columns=['同比上年'],
                percentage_columns=['同比上年'],
                indicator_name_column='年度指标名称',
                date_column='最新年份',
                column_order=[
                    '年度指标名称', '最新年份', '最新值', '上年值', '同比上年',
                    '两年前值', '三年前值'
                ],
                color='#9467bd'
            ),
            'quarterly': FrequencyConfig(
                english_name='quarterly',
                display_name='季度',
                sort_column='环比上季',
                highlight_columns=['环比上季', '同比上年'],
                percentage_columns=['环比上季', '同比上年'],
                indicator_name_column='季度指标名称',
                date_column='最新季度',
                column_order=[
                    '季度指标名称', '最新季度', '最新值', '上季值',
                    '环比上季', '上年同季值', '同比上年'
                ],
                color='#8c564b'
            )
        }

    def _build_colors(self) -> Dict[str, str]:
        """构建颜色配置"""
        return {
            'current_year': 'red',
            'previous_year': 'blue',
            'historical_mean': 'grey',
            'historical_range': 'rgba(211, 211, 211, 0.5)',
            'positive': '#ffcdd2',
            'negative': '#c8e6c9'
        }

    def _build_ui_text(self) -> Dict[str, str]:
        """构建UI文本配置"""
        return {
            'select_industry': '选择行业大类',
            'select_type': '选择指标类型',
            'all_option': '全部',
            'download_label': '下载数据摘要 (CSV)',
            'no_data_warning': '筛选条件 "{}" 没有匹配的指标。',
            'loading_message': '正在生成 {} 的图表...',
            'empty_data': '{}数据尚未加载或为空,请返回"数据概览"模块上传数据。'
        }

    def _build_plot_config(self) -> Dict[str, Any]:
        """构建绘图配置"""
        return {
            'weekly': {
                'x_range': range(1, 54),
                'x_label_func': lambda x: f"W{x}",
                'x_tick_interval': 4,
                'historical_years': 5,
                'layout': {
                    'margin': {'l': 50, 'r': 30, 't': 60, 'b': 120},
                    'legend': {
                        'orientation': 'h',
                        'yanchor': 'bottom',
                        'y': -0.3,
                        'xanchor': 'center',
                        'x': 0.5
                    }
                }
            },
            'monthly': {
                'x_range': range(1, 13),
                'x_label_func': lambda x: f"{x}月",
                'x_tick_interval': 1,
                'historical_years': 5,
                'layout': {
                    'margin': {'l': 50, 'r': 30, 't': 60, 'b': 120},
                    'legend': {
                        'orientation': 'h',
                        'yanchor': 'bottom',
                        'y': -0.3,
                        'xanchor': 'center',
                        'x': 0.5
                    }
                }
            },
            'daily': {
                'x_range': range(1, 367),
                'x_label_func': lambda x: f"{x}日",
                'x_tick_vals': [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335],
                'x_tick_labels': ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
                'historical_years': 5,
                'layout': {
                    'margin': {'l': 50, 'r': 30, 't': 60, 'b': 120},
                    'legend': {
                        'orientation': 'h',
                        'yanchor': 'bottom',
                        'y': -0.3,
                        'xanchor': 'center',
                        'x': 0.5
                    }
                }
            },
            'ten_day': {
                'x_range': range(1, 37),
                'x_label_func': lambda x: f"第{x}旬",
                'x_tick_vals': [i - 0.5 for i in range(1, 38, 3)],  # 标签在月初位置：0.5, 3.5, 6.5, ...
                'x_tick_labels': [f"{i}月" for i in range(1, 13)] + [''],  # 13个标签位置
                'historical_years': 5,
                'layout': {
                    'margin': {'l': 50, 'r': 30, 't': 60, 'b': 120},
                    'legend': {
                        'orientation': 'h',
                        'yanchor': 'bottom',
                        'y': -0.3,
                        'xanchor': 'center',
                        'x': 0.5
                    }
                }
            },
            'yearly': {
                'layout': {
                    'margin': {'l': 50, 'r': 30, 't': 60, 'b': 100}
                }
            },
            'quarterly': {
                'x_range': range(1, 5),
                'x_label_func': lambda x: f"Q{x}",
                'x_tick_interval': 1,
                'historical_years': 5,
                'layout': {
                    'margin': {'l': 50, 'r': 30, 't': 60, 'b': 120},
                    'legend': {
                        'orientation': 'h',
                        'yanchor': 'bottom',
                        'y': -0.3,
                        'xanchor': 'center',
                        'x': 0.5
                    }
                }
            }
        }

    def _build_summary_config(self) -> Dict[str, Any]:
        """构建摘要配置"""
        configs = {}
        for freq_name in self._frequencies:
            freq_config = self._frequency_configs[freq_name]
            configs[freq_name] = {
                'indicator_name_column': freq_config.indicator_name_column,
                'date_column': freq_config.date_column,
                'column_order': freq_config.column_order,
                'sort_column': freq_config.sort_column,
                'highlight_columns': freq_config.highlight_columns,
                'percentage_columns': freq_config.percentage_columns,
            }
        return configs


# 导出配置变量供共享组件使用
UNIFIED_FREQUENCY_CONFIGS = {}
FREQUENCY_ORDER = ['日度', '周度', '旬度', '月度', '季度', '年度']
CHINESE_TO_ENGLISH_FREQ = {
    '周度': 'weekly',
    '月度': 'monthly',
    '日度': 'daily',
    '旬度': 'ten_day',
    '季度': 'quarterly',
    '年度': 'yearly'
}
ENGLISH_TO_CHINESE_FREQ = {v: k for k, v in CHINESE_TO_ENGLISH_FREQ.items()}

# 指标字典中频率字符到英文标识的映射（单字格式）
FREQ_CHAR_TO_ENGLISH = {
    '日': 'daily',
    '周': 'weekly',
    '旬': 'ten_day',
    '月': 'monthly',
    '季': 'quarterly',
    '年': 'yearly'
}

# 初始化配置
_config = IndustrialConfig()
for freq in _config.get_frequencies():
    freq_cfg = _config.get_frequency_config(freq)
    UNIFIED_FREQUENCY_CONFIGS[freq] = {
        'english_name': freq_cfg.english_name,
        'display_name': freq_cfg.display_name,
        'key_prefix': freq,
        'df_key': f'{freq}_df',
        'industries_key': f'{freq}_industries',
        'empty_message': f'{freq_cfg.display_name}数据尚未加载或为空,请返回"数据概览"模块上传数据。',
        'summary_config': {
            'sort_column': freq_cfg.sort_column,
            'highlight_columns': freq_cfg.highlight_columns,
            'percentage_columns': freq_cfg.percentage_columns,
            'download_prefix': f'{freq_cfg.display_name}数据摘要'
        }
    }

COLORS = _config.get_colors()
UI_TEXT = _config.get_ui_text()
PLOT_CONFIGS = _config.get_plot_config()
SUMMARY_CONFIGS = _config.get_summary_config()
