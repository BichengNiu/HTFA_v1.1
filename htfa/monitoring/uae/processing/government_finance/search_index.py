from __future__ import annotations
import pandas as pd
from scipy.signal import savgol_filter
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.contracts.government_finance.search_index import SMOOTH_WINDOW
from htfa.monitoring.uae.contracts.government_finance.search_index import (
    SMOOTH_POLYORDER,
)
from htfa.monitoring.uae.contracts.government_finance.search_index import SEARCH_SERIES
from htfa.monitoring.uae.contracts.government_finance.search_index import START_YEAR
from htfa.monitoring.uae.data.government_finance.search_index import (
    read_search_index_data,
)


def load_search_index_data(source: PublishedUAEData) -> pd.DataFrame:
    """从 DuckDB 的 ``月度_工作搜索热度`` 读取谷歌趋势序列。"""
    (values,) = read_search_index_data(source)
    values.index = pd.DatetimeIndex(values.index).normalize()
    return values


def display_search_index_values(values: pd.DataFrame) -> pd.DataFrame:
    """返回标准化绘图序列及原始、平滑中间值，日期对齐月末。"""
    display = values.loc[values.index >= pd.Timestamp(START_YEAR, 1, 1)].copy()
    display.index = display.index.to_period("M").to_timestamp("M")
    result = pd.DataFrame(index=display.index)
    for column, label in SEARCH_SERIES:
        smoothed = _smooth_series(display[column])
        result[label] = _standardize_series(smoothed)
        result[f"{label}（原始指数）"] = display[column]
        result[f"{label}（平滑指数）"] = smoothed
    return result


def _smooth_series(series: pd.Series) -> pd.Series:
    """用 Savitzky-Golay 平滑曲线，接近谷歌趋势的展示效果。"""
    values = series.dropna().astype(float)
    window = min(SMOOTH_WINDOW, len(values))
    if window % 2 == 0:
        window -= 1
    if window < 3 or values.nunique() == 1:
        return series
    return pd.Series(
        savgol_filter(values.to_numpy(), window, SMOOTH_POLYORDER), index=values.index
    )


def _standardize_series(series: pd.Series) -> pd.Series:
    """Z-score 标准化，使不同关键词热度可在同一坐标轴上比较。"""
    values = series.dropna().astype(float)
    std = values.std()
    if values.empty:
        return values
    if pd.isna(std) or std == 0:
        raise ValueError("搜索热度缺少足够变动，无法计算标准化指数")
    return (values - values.mean()) / std
