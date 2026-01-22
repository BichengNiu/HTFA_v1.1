"""
Time Range Filter Utility
时间范围过滤工具 - 统一的时间范围过滤函数

消除重复代码:
- 原 enterprise_operations.py:362-428 (67行)
- 原 data_processor.py:225-291 (67行)
"""

import pandas as pd
from typing import Optional


def filter_data_by_time_range(
    df: pd.DataFrame,
    time_range: str,
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None
) -> pd.DataFrame:
    """
    根据时间范围过滤DataFrame

    Args:
        df: 输入的DataFrame，索引必须是DatetimeIndex
        time_range: 时间范围选项 ("1年", "3年", "5年", "全部", "自定义")
        custom_start_date: 自定义开始日期 (YYYY-MM格式)
        custom_end_date: 自定义结束日期 (YYYY-MM格式)

    Returns:
        过滤后的DataFrame
    """
    # 如果是全部或数据为空，直接返回副本
    if df.empty or time_range == "全部":
        return df.copy()

    # 获取数据集中的最新日期
    latest_date = df.index.max()

    # 处理自定义日期范围
    if time_range == "自定义" and custom_start_date and custom_end_date:
        try:
            start_date = pd.to_datetime(custom_start_date + "-01")
            end_date = pd.to_datetime(custom_end_date + "-01") + pd.offsets.MonthEnd(0)
        except (ValueError, TypeError):
            # 解析失败，使用全部数据
            start_date = df.index.min()
            end_date = df.index.max()
    else:
        # 根据时间范围选择计算开始日期（从最新日期向前推算）
        if time_range == "1年":
            start_date = latest_date - pd.DateOffset(years=1)
        elif time_range == "3年":
            start_date = latest_date - pd.DateOffset(years=3)
        elif time_range == "5年":
            start_date = latest_date - pd.DateOffset(years=5)
        elif time_range == "自定义":
            # 自定义范围但未提供日期，使用全部数据
            start_date = df.index.min()
            end_date = df.index.max()
        else:
            # 默认使用全部数据
            start_date = df.index.min()
            end_date = df.index.max()

        # 非自定义范围时，结束日期为最新日期
        if time_range != "自定义":
            end_date = latest_date

    # 使用日期范围过滤数据
    try:
        # 确保索引是DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # 使用布尔索引过滤
        if time_range == "自定义":
            mask = (df.index >= start_date) & (df.index <= end_date)
        else:
            mask = df.index >= start_date

        return df.loc[mask].copy()

    except Exception:
        # 如果日期过滤失败，使用tail方法作为后备
        if time_range == "1年":
            return df.tail(12)
        elif time_range == "3年":
            return df.tail(36)
        elif time_range == "5年":
            return df.tail(60)
        else:
            return df.copy()
