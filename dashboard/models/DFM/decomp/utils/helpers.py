# -*- coding: utf-8 -*-
"""
辅助函数模块

提供日期范围计算等辅助功能。
变量名标准化统一使用 dashboard.models.DFM.utils.text_utils。
"""

import pandas as pd
from typing import Tuple


def get_month_date_range(target_date: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """
    计算目标日期所在月份的起止日期

    Args:
        target_date: 目标日期

    Returns:
        (month_start, month_end) 元组
    """
    month_start = target_date.to_period('M').to_timestamp()
    month_end = month_start + pd.offsets.MonthEnd(0)
    return month_start, month_end
