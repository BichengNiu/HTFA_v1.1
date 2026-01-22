# -*- coding: utf-8 -*-
"""
周五计算工具模块

提供统一的周五日期计算功能，用于：
- 数据对齐（将不同频率数据对齐到周五）
- 发布日期校准（根据滞后天数计算发布日期对应的周五）

所有周五计算逻辑集中在此模块，消除重复代码。
"""

import pandas as pd
from calendar import monthrange
from typing import Tuple


def get_nearest_friday(dt: pd.Timestamp) -> pd.Timestamp:
    """
    计算给定日期的最近周五

    规则：
    - 周一到周五: 对齐到本周五
    - 周六日: 对齐到上周五

    Args:
        dt: 日期对象

    Returns:
        pd.Timestamp: 最近的周五日期
    """
    weekday = dt.weekday()
    if weekday <= 4:  # 周一到周五
        days_to_friday = 4 - weekday
    else:  # 周六日
        days_to_friday = -(weekday - 4)
    return dt + pd.Timedelta(days=days_to_friday)


def _get_last_friday_of_month(year: int, month: int) -> pd.Timestamp:
    """获取指定月份的最后一个周五"""
    last_day = monthrange(year, month)[1]
    last_date = pd.Timestamp(year, month, last_day)
    last_wd = last_date.weekday()
    if last_wd >= 4:  # 周五、周六、周日
        days_back = last_wd - 4
    else:  # 周一到周四
        days_back = last_wd + 3
    return last_date - pd.Timedelta(days=days_back)


def _get_first_friday_of_month(year: int, month: int) -> pd.Timestamp:
    """获取指定月份的第一个周五"""
    first_date = pd.Timestamp(year, month, 1)
    first_wd = first_date.weekday()
    if first_wd <= 4:  # 周一到周五
        days_forward = 4 - first_wd
    else:  # 周六日
        days_forward = 11 - first_wd
    return first_date + pd.Timedelta(days=days_forward)


def get_monthly_friday(dt: pd.Timestamp) -> pd.Timestamp:
    """
    计算给定日期所属月份内的周五（不跨月）

    规则：
    - 首先计算最近周五
    - 如果跨到下个月，返回当月最后一个周五
    - 如果跨到上个月，返回当月第一个周五

    Args:
        dt: 日期对象

    Returns:
        pd.Timestamp: 当月内的周五日期
    """
    year = dt.year
    month = dt.month

    target_friday = get_nearest_friday(dt)

    # 检查是否跨月
    if target_friday.month != month:
        if target_friday.month > month or (target_friday.month == 1 and month == 12):
            # 跨到下个月 -> 当月最后一个周五
            target_friday = _get_last_friday_of_month(year, month)
        else:
            # 跨到上个月 -> 当月第一个周五
            target_friday = _get_first_friday_of_month(year, month)

    return target_friday


def get_quarterly_friday(dt: pd.Timestamp) -> pd.Timestamp:
    """
    计算给定日期所属季度内的周五（不跨季）

    规则：
    - 首先计算最近周五
    - 如果跨到下个季度，返回当季最后一个周五
    - 如果跨到上个季度，返回当季第一个周五

    Args:
        dt: 日期对象

    Returns:
        pd.Timestamp: 当季内的周五日期
    """
    year = dt.year
    month = dt.month
    quarter = (month - 1) // 3 + 1  # 1, 2, 3, 4
    quarter_start_month = (quarter - 1) * 3 + 1  # 1, 4, 7, 10
    quarter_end_month = quarter * 3  # 3, 6, 9, 12

    target_friday = get_nearest_friday(dt)
    target_quarter = (target_friday.month - 1) // 3 + 1

    # 检查是否跨季
    if target_friday.year != year or target_quarter != quarter:
        if (target_friday.year > year) or (target_friday.year == year and target_quarter > quarter):
            # 跨到下个季度 -> 当季最后一个周五
            target_friday = _get_last_friday_of_month(year, quarter_end_month)
        else:
            # 跨到上个季度 -> 当季第一个周五
            target_friday = _get_first_friday_of_month(year, quarter_start_month)

    return target_friday


def get_yearly_friday(dt: pd.Timestamp) -> pd.Timestamp:
    """
    计算给定日期所属年份内的周五（不跨年）

    规则：
    - 首先计算最近周五
    - 如果跨到下一年，返回当年最后一个周五
    - 如果跨到上一年，返回当年第一个周五

    Args:
        dt: 日期对象

    Returns:
        pd.Timestamp: 当年内的周五日期
    """
    year = dt.year

    target_friday = get_nearest_friday(dt)

    # 检查是否跨年
    if target_friday.year != year:
        if target_friday.year > year:
            # 跨到下一年 -> 当年最后一个周五（12月）
            target_friday = _get_last_friday_of_month(year, 12)
        else:
            # 跨到上一年 -> 当年第一个周五（1月）
            target_friday = _get_first_friday_of_month(year, 1)

    return target_friday


def get_dekad_friday(dt: pd.Timestamp) -> pd.Timestamp:
    """
    将旬日对齐到最近的周五（不跨月）

    规则：
    - 周一：上周五更近
    - 周二到周五：本周五更近
    - 周六日：上周五更近
    - 如果对齐后跨月，则调整到当月最后/第一个周五

    Args:
        dt: 旬日日期对象

    Returns:
        pd.Timestamp: 当月内的周五日期
    """
    year = dt.year
    month = dt.month
    weekday = dt.weekday()

    if weekday == 0:  # 周一
        days_to_friday = -3
    elif weekday <= 4:  # 周二到周五
        days_to_friday = 4 - weekday
    else:  # 周六日
        days_to_friday = -(weekday - 4)

    target_friday = dt + pd.Timedelta(days=days_to_friday)

    # 检查是否跨月
    if target_friday.month != month:
        if target_friday.month > month or (target_friday.month == 1 and month == 12):
            # 跨到下个月 -> 当月最后一个周五
            target_friday = _get_last_friday_of_month(year, month)
        else:
            # 跨到上个月 -> 当月第一个周五
            target_friday = _get_first_friday_of_month(year, month)

    return target_friday


# ============================================================================
# 发布日期校准专用函数（带滞后天数）
# ============================================================================

def get_friday_with_lag(
    data_date: pd.Timestamp,
    lag_days: int,
    period_type: str = 'month'
) -> pd.Timestamp:
    """
    计算发布日期附近的周五（用于发布日期校准）

    逻辑：
    1. 数据日期 + 滞后天数 = 发布日期
    2. 对齐到发布日期最近的周五
    3. 如果最近周五跨越边界，则调整到发布周期内的周五

    Args:
        data_date: 数据日期（如月度数据的月末日期）
        lag_days: 滞后天数（如15表示下月15日发布）
        period_type: 周期类型 ('month', 'quarter', 'year')

    Returns:
        pd.Timestamp: 发布日期附近的周五（在发布周期内）
    """
    # 实际发布日期 = 数据日期 + 滞后天数
    pub_date = data_date + pd.Timedelta(days=lag_days)

    if period_type == 'month':
        return _get_friday_within_month(pub_date)
    elif period_type == 'quarter':
        return _get_friday_within_quarter(pub_date)
    elif period_type == 'year':
        return _get_friday_within_year(pub_date)
    else:
        # 默认返回最近周五（不限制边界）
        return get_nearest_friday(pub_date)


def _get_friday_within_month(pub_date: pd.Timestamp) -> pd.Timestamp:
    """在发布月份内找到周五"""
    year, month = pub_date.year, pub_date.month

    target_friday = get_nearest_friday(pub_date)

    # 检查是否跨月
    if target_friday.month != month:
        if target_friday.month > month or (target_friday.month == 1 and month == 12):
            # 跨到下个月 -> 发布月份的最后一个周五
            target_friday = _get_last_friday_of_month(year, month)
        else:
            # 跨到上个月 -> 发布月份的第一个周五
            target_friday = _get_first_friday_of_month(year, month)

    return target_friday


def _get_friday_within_quarter(pub_date: pd.Timestamp) -> pd.Timestamp:
    """在发布季度内找到周五"""
    year = pub_date.year
    month = pub_date.month
    quarter = (month - 1) // 3 + 1
    quarter_start_month = (quarter - 1) * 3 + 1
    quarter_end_month = quarter * 3

    target_friday = get_nearest_friday(pub_date)
    target_quarter = (target_friday.month - 1) // 3 + 1

    # 检查是否跨季
    if target_friday.year != year or target_quarter != quarter:
        if (target_friday.year > year) or (target_friday.year == year and target_quarter > quarter):
            # 跨到下个季度 -> 发布季度的最后一个周五
            target_friday = _get_last_friday_of_month(year, quarter_end_month)
        else:
            # 跨到上个季度 -> 发布季度的第一个周五
            target_friday = _get_first_friday_of_month(year, quarter_start_month)

    return target_friday


def _get_friday_within_year(pub_date: pd.Timestamp) -> pd.Timestamp:
    """在发布年份内找到周五"""
    year = pub_date.year

    target_friday = get_nearest_friday(pub_date)

    # 检查是否跨年
    if target_friday.year != year:
        if target_friday.year > year:
            # 跨到下一年 -> 发布年份的最后一个周五
            target_friday = _get_last_friday_of_month(year, 12)
        else:
            # 跨到上一年 -> 发布年份的第一个周五
            target_friday = _get_first_friday_of_month(year, 1)

    return target_friday


__all__ = [
    'get_nearest_friday',
    'get_monthly_friday',
    'get_quarterly_friday',
    'get_yearly_friday',
    'get_dekad_friday',
    'get_friday_with_lag',
]
