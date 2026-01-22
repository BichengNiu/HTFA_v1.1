"""
工具模块包

提供数据准备过程中常用的工具函数：
- text_utils: 文本标准化处理
- date_utils: 日期处理
- friday_utils: 周五计算工具
- html_helpers: HTML生成辅助函数
"""

from dashboard.models.DFM.utils.text_utils import normalize_text, normalize_column_name
from dashboard.models.DFM.prep.utils.date_utils import standardize_date, parse_date_range, filter_by_date_range
from dashboard.models.DFM.prep.utils.friday_utils import (
    get_nearest_friday,
    get_monthly_friday,
    get_quarterly_friday,
    get_yearly_friday,
    get_dekad_friday,
    get_friday_with_lag,
)
from dashboard.models.DFM.prep.utils.html_helpers import (
    DEFAULT_TAG_STYLE,
    render_tag,
    render_tag_group,
    render_grouped_tags,
)

__all__ = [
    # text_utils
    'normalize_text',
    'normalize_column_name',
    # date_utils
    'standardize_date',
    'parse_date_range',
    'filter_by_date_range',
    # friday_utils
    'get_nearest_friday',
    'get_monthly_friday',
    'get_quarterly_friday',
    'get_yearly_friday',
    'get_dekad_friday',
    'get_friday_with_lag',
    # html_helpers
    'DEFAULT_TAG_STYLE',
    'render_tag',
    'render_tag_group',
    'render_grouped_tags',
]
