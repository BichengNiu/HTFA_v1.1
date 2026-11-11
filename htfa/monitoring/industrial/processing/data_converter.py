"""
Data Converter Utility
数据转换工具 - 统一的数据转换函数

主要功能:
- convert_cumulative_to_yoy: 将累计值转换为年同比
- convert_margin_to_yoy_diff: 将利润率累计值转换为年同比差值（百分点）
- convert_cumulative_to_current: 将累计值转换为当期值
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def _prior_year_values(data_series: pd.Series, periods: int) -> tuple[pd.Series, pd.Series]:
    """将序列与去年同期对齐。

    返回 (当前值, 去年同期的值)；两者索引对齐，缺失处为 NaN。
    """
    data_series = pd.to_numeric(data_series, errors='coerce')
    data_series = data_series.sort_index()

    # 创建12个月前的日期索引
    prev_dates = data_series.index - pd.DateOffset(months=periods)

    # 使用reindex获取12个月前的值（带容差匹配，30天内）
    # reindex的nearest方法会自动找到最接近的日期
    tolerance = pd.Timedelta(days=30)
    prev_values = data_series.reindex(prev_dates, method='nearest', tolerance=tolerance)

    # 将prev_values的索引对齐到当前索引（用于向量化计算）
    prev_values.index = data_series.index

    return data_series, prev_values


def _mask_jan_feb(series: pd.Series) -> pd.Series:
    """将1月和2月的值设为NaN（累计值在这两个月不具有可比性）。"""
    jan_feb_mask = (series.index.month == 1) | (series.index.month == 2)
    series.loc[jan_feb_mask] = float('nan')
    return series


def convert_cumulative_to_yoy(data_series: pd.Series, periods: int = 12) -> pd.Series:
    """
    将累计值转换为年同比数据，并将1、2月设为缺失值（向量化优化版本）

    该函数用于处理累计值指标(如累计利润总额)，计算其年同比增长率。
    由于1月和2月的累计值不具有可比性，这两个月的值将设为NaN。

    Args:
        data_series: 累计值数据序列，索引应为DatetimeIndex
        periods: 年同比的期数，默认12个月

    Returns:
        年同比数据序列 (单位: 百分比)
    """
    try:
        current_values, prev_values = _prior_year_values(data_series, periods)

        # 向量化计算年同比：((current - prev) / prev) * 100
        yoy_series = ((current_values - prev_values) / prev_values) * 100

        return _mask_jan_feb(yoy_series)

    except Exception:
        logger.exception("累计值转年同比失败")
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
    """
    try:
        current_values, prev_values = _prior_year_values(data_series, periods)

        # 差值法：当期 - 去年同期（单位：百分点）
        yoy_diff = current_values - prev_values

        return _mask_jan_feb(yoy_diff)

    except Exception:
        logger.exception("利润率转年同比差值失败")
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

    Args:
        data_series: 累计值数据序列，索引应为DatetimeIndex

    Returns:
        当期值数据序列（单位与输入相同）
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
        logger.exception("累计值转当期值失败")
        return pd.Series()
