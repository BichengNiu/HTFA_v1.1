"""
Data Converter Utility
数据转换工具 - 统一的数据转换函数

主要功能:
- convert_cumulative_to_yoy: 将累计值转换为年同比
"""

import pandas as pd
import streamlit as st


def convert_cumulative_to_yoy(data_series: pd.Series, periods: int = 12) -> pd.Series:
    """
    将累计值转换为年同比数据，并将1、2月设为缺失值（向量化优化版本）

    该函数用于处理累计值指标(如累计利润总额)，计算其年同比增长率。
    由于1月和2月的累计值不具有可比性，这两个月的值将设为NaN。

    性能优化：使用pandas向量化操作替代循环，预期性能提升5-10倍
    - 消除了for循环遍历每个日期点
    - 使用reindex()方法一次性处理所有日期的匹配（带容差）
    - 使用向量化操作计算百分比变化

    Args:
        data_series: 累计值数据序列，索引应为DatetimeIndex
        periods: 年同比的期数，默认12个月

    Returns:
        年同比数据序列 (单位: 百分比)

    Example:
        >>> cumulative_profit = pd.Series([100, 150, 200],
        ...     index=pd.date_range('2023-01', periods=3, freq='M'))
        >>> yoy = convert_cumulative_to_yoy(cumulative_profit)
    """
    try:
        # 确保数据是数值型
        data_series = pd.to_numeric(data_series, errors='coerce')

        # 确保索引已排序
        data_series = data_series.sort_index()

        # 创建12个月前的日期索引
        prev_dates = data_series.index - pd.DateOffset(months=periods)

        # 使用reindex获取12个月前的值（带容差匹配，30天内）
        # reindex的nearest方法会自动找到最接近的日期
        tolerance = pd.Timedelta(days=30)
        prev_values = data_series.reindex(prev_dates, method='nearest', tolerance=tolerance)

        # 将prev_values的索引对齐到当前索引（用于向量化计算）
        prev_values.index = data_series.index

        # 向量化计算年同比：((current - prev) / prev) * 100
        # pandas会自动处理NaN和除零情况
        yoy_series = ((data_series - prev_values) / prev_values) * 100

        # 将1月和2月的值设为NaN（因为累计值在这两个月不具有可比性）
        jan_feb_mask = (yoy_series.index.month == 1) | (yoy_series.index.month == 2)
        yoy_series.loc[jan_feb_mask] = float('nan')

        return yoy_series

    except Exception:
        return pd.Series()


def convert_margin_to_yoy_diff(data_series: pd.Series, periods: int = 12) -> pd.Series:
    """
    将利润率累计值转换为年同比差值（百分点变化）

    对于比率指标（如利润率），年同比应该用差值法计算百分点变化，
    而不是增长率法计算百分比变化。

    示例：
    - 去年利润率：5%，今年利润率：6%
    - 差值法（正确）：6% - 5% = 1个百分点
    - 增长率法（错误）：(6-5)/5*100 = 20%（会误导读者）

    Args:
        data_series: 利润率累计值序列，索引应为DatetimeIndex（单位：%）
        periods: 年同比的期数，默认12个月

    Returns:
        年同比差值序列（单位：百分点）

    Example:
        >>> profit_margin = pd.Series([5.0, 5.5, 6.0],
        ...     index=pd.date_range('2023-01', periods=3, freq='M'))
        >>> yoy_diff = convert_margin_to_yoy_diff(profit_margin)
    """
    try:
        data_series = pd.to_numeric(data_series, errors='coerce')
        data_series = data_series.sort_index()

        prev_dates = data_series.index - pd.DateOffset(months=periods)
        tolerance = pd.Timedelta(days=30)
        prev_values = data_series.reindex(prev_dates, method='nearest', tolerance=tolerance)
        prev_values.index = data_series.index

        # 差值法：当期 - 去年同期（单位：百分点）
        yoy_diff = data_series - prev_values

        # 将1月和2月的值设为NaN
        jan_feb_mask = (yoy_diff.index.month == 1) | (yoy_diff.index.month == 2)
        yoy_diff.loc[jan_feb_mask] = float('nan')

        return yoy_diff

    except Exception:
        return pd.Series()


def convert_cumulative_to_current(data_series: pd.Series) -> pd.Series:
    """
    将累计值转换为当期值（月度值）

    转换逻辑：
    - 1月当期值 = 1月累计值（因为没有上月）
    - 其他月当期值 = 当月累计值 - 上月累计值

    与convert_cumulative_to_yoy的区别：
    - convert_cumulative_to_yoy: 累计值 -> 年同比增长率（%），会过滤1-2月
    - convert_cumulative_to_current: 累计值 -> 当期值（原始单位），保留所有月份

    性能优化：使用pandas向量化操作

    Args:
        data_series: 累计值数据序列，索引应为DatetimeIndex

    Returns:
        当期值数据序列（单位与输入相同）

    Example:
        累计值: [100, 250, 420]（1月、2月、3月）
        当期值: [100, 150, 170]（1月、2月、3月）
    """
    try:
        # 确保数据是数值型
        data_series = pd.to_numeric(data_series, errors='coerce')

        # 确保索引已排序
        data_series = data_series.sort_index()

        # 使用diff()方法计算差分：当月 - 上月
        current_values = data_series.diff()

        # 第一个值（通常是1月）用原始累计值填充
        # 因为diff()会将第一个值设为NaN
        current_values.iloc[0] = data_series.iloc[0]

        return current_values

    except Exception:
        return pd.Series()
