"""SARIMAX 预测规划的纯逻辑。

本模块只处理预测前后的日期、外生变量和真实值对齐，不依赖
Streamlit、Matplotlib 或 Ts。页面层据此准备统一的预测请求和展示数据。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from dashboard.models.SARIMAX.core.data_loader import (
    dataset_time_index,
    forecast_sample_dates,
)


@dataclass(frozen=True)
class ForecastCalendar:
    """预测滑轨使用的模型日历、数据集日历和可外推日历。

    Parameters
    ----------
    model_dates : pandas.DatetimeIndex or None
        拟合结果对应的有效样本日期。
    base_dates : pandas.DatetimeIndex or None
        模型日期与数据集中训练结束日之后日期合并后的日期。
    dates : pandas.DatetimeIndex or None
        在 ``base_dates`` 末端追加有限未来日期后的完整滑轨日期。
    """

    model_dates: pd.DatetimeIndex | None
    base_dates: pd.DatetimeIndex | None
    dates: pd.DatetimeIndex | None


def normalise_model_dates(
    dates: Any,
) -> pd.DatetimeIndex | None:
    """规范化模型有效日期索引。

    Parameters
    ----------
    dates : sequence of datetime-like or None
        模型适配器提取出的有效日期序列；没有日期模型时为 ``None``。

    Returns
    -------
    pandas.DatetimeIndex or None
        去重后的日期索引；结果没有日期时返回 ``None``。
    """
    if dates is None:
        return None
    return pd.DatetimeIndex(pd.to_datetime(dates)).drop_duplicates()


def build_forecast_calendar(
    dataset: Any,
    model_dates: pd.DatetimeIndex | None,
    training_end: pd.Timestamp,
    extension_periods: int = 12,
) -> ForecastCalendar:
    """构造预测滑轨所需的模型、观测和未来日期。

    Parameters
    ----------
    dataset : OverviewDataset or None
        当前数据概览数据集，用于补充训练结束日之后的观测日期和推断频率。
    model_dates : pandas.DatetimeIndex or None
        模型适配器提供的有效样本日期。
    training_end : pandas.Timestamp or datetime-like
        训练样本结束日期；该日期本身属于训练样本。
    extension_periods : int, default=12
        在当前日期日历末端追加的未来期数；小于等于零时不追加。

    Returns
    -------
    ForecastCalendar
        包含模型有效日期、已有观测日期和有限外推日期的日历结构。

    Raises
    ------
    ValueError
        模型没有有效日期，或无法从数据集/模型日期推断追加频率。
    """
    if model_dates is None:
        raise ValueError("模型没有有效日期索引")
    model_dates = normalise_model_dates(model_dates)

    observed_future = (
        forecast_sample_dates(dataset, training_end)
        if dataset is not None
        else None
    )
    base_dates = model_dates
    if observed_future is not None and len(observed_future):
        base_dates = base_dates.append(pd.DatetimeIndex(observed_future))
    base_dates = base_dates.sort_values().drop_duplicates()

    dates = base_dates
    if extension_periods > 0:
        offset = _infer_calendar_offset(dataset, model_dates)
        extension = pd.date_range(
            start=base_dates[-1] + offset,
            periods=int(extension_periods),
            freq=offset,
        )
        dates = base_dates.append(extension)

    return ForecastCalendar(
        model_dates=model_dates,
        base_dates=base_dates,
        dates=dates,
    )


def normalise_date_window(
    value: Any,
    options: tuple[date, ...],
) -> tuple[date, date] | None:
    """校验日期滑轨已有值是否仍属于当前日历。

    Parameters
    ----------
    value : object
        Streamlit 日期滑轨保存的候选值，通常是两个日期组成的元组或列表。
    options : tuple of datetime.date
        当前日期滑轨允许的有序日期选项。

    Returns
    -------
    tuple[datetime.date, datetime.date] or None
        合法且有序的日期窗口；值无效或不在选项中时返回 ``None``。
    """
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        window = tuple(pd.Timestamp(item).date() for item in value)
    except (TypeError, ValueError):
        return None
    if window[0] > window[1] or any(item not in options for item in window):
        return None
    return window


def resolve_prediction_positions(
    calendar: pd.DatetimeIndex,
    selected_window: tuple[date, date],
) -> tuple[int, int]:
    """把日期滑轨窗口转换为 Ts 使用的闭区间位置。

    Parameters
    ----------
    calendar : pandas.DatetimeIndex
        预测滑轨的完整日期日历。
    selected_window : tuple[datetime.date, datetime.date]
        用户选择的起始日期和结束日期。

    Returns
    -------
    tuple[int, int]
        对应的起始和结束位置，结束位置包含在预测窗口内。

    Raises
    ------
    ValueError
        选择的日期不在日历中，或起始日期晚于结束日期。
    """
    dates = tuple(pd.Timestamp(value).date() for value in calendar)
    positions = {value: index for index, value in enumerate(dates)}
    start_date, end_date = selected_window
    if start_date not in positions or end_date not in positions:
        raise ValueError("预测滑轨日期不在当前数据日历中")
    start = positions[start_date]
    end = positions[end_date]
    if start > end:
        raise ValueError("预测起始日期不能晚于预测结束日期")
    return start, end


def future_dates(
    dates: pd.DatetimeIndex | None,
    steps: int,
    fallback_dates: pd.DatetimeIndex | None = None,
) -> pd.DatetimeIndex | None:
    """基于拟合日期频率推算未来预测日期。

    Parameters
    ----------
    dates : pandas.DatetimeIndex or None
        模型适配器提供的有效日期序列。
    steps : int
        需要生成的未来期数。
    fallback_dates : pandas.DatetimeIndex or None, optional
        拟合数据因缺失值而不连续时，用于补充推断频率的完整日期。

    Returns
    -------
    pandas.DatetimeIndex or None
        从拟合结果最后日期开始生成的未来日期；无法推断频率时返回 ``None``。
    """
    if dates is None or len(dates) == 0:
        return None
    dates = normalise_model_dates(dates)
    if dates is None or len(dates) == 0:
        return None
    freq = dates.freq
    if freq is None:
        freq = pd.infer_freq(dates)
    if freq is None and fallback_dates is not None:
        fallback = pd.DatetimeIndex(fallback_dates)
        freq = fallback.freq or pd.infer_freq(fallback)
    if freq is None:
        return None
    offset = pd.tseries.frequencies.to_offset(freq)
    return pd.date_range(
        start=dates[-1] + offset,
        periods=steps,
        freq=offset,
    )


def build_future_exog(
    dataset: Any,
    model_nobs: int,
    model_dates: pd.DatetimeIndex | None,
    total_steps: int,
    source_columns: tuple[str, ...],
    exog_names: tuple[str, ...],
    forecast_dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """按拟合结果的未来日历提取外生变量路径。

    Parameters
    ----------
    dataset : OverviewDataset or None
        当前数据概览数据集；为 ``None`` 时返回全为空值的路径。
    model_nobs : int
        模型适配器提供的有效样本数，用于无日期数据的位置切片。
    model_dates : pandas.DatetimeIndex or None
        模型适配器提供的有效样本日期，用于推断未来频率。
    total_steps : int
        从拟合样本末期开始需要准备的未来期数。
    source_columns : tuple[str, ...]
        数据集中的来源列，按位置对应 ``exog_names``。
    exog_names : tuple[str, ...]
        模型外生变量名，作为返回表的列名。
    forecast_dates : pandas.DatetimeIndex or None, optional
        已经由页面规划好的完整未来日期；提供后优先使用。

    Returns
    -------
    pandas.DataFrame
        以未来日期或位置为索引、以模型外生变量名为列的路径表。
        无法取得数据的单元格保留为 ``NaN``。
    """
    index = _future_index(model_dates, total_steps, forecast_dates)
    if dataset is None:
        return pd.DataFrame(np.nan, index=index, columns=exog_names)

    frame = dataset.frame.copy()
    if dataset.time_column is not None:
        dates = pd.DatetimeIndex(pd.to_datetime(frame[dataset.time_column]))
        frame = frame.drop(columns=[dataset.time_column])
        frame.index = dates
        frame = frame.sort_index()
        index = (
            pd.DatetimeIndex(forecast_dates)
            if forecast_dates is not None
            else future_dates(model_dates, total_steps, fallback_dates=dates)
        )
        if index is None:
            index = pd.RangeIndex(total_steps)
        values = {
            model_name: pd.to_numeric(frame[source], errors="coerce").reindex(index)
            for model_name, source in zip(exog_names, source_columns)
        }
        return pd.DataFrame(values, index=index)

    values = {}
    for model_name, source in zip(exog_names, source_columns):
        series = pd.to_numeric(frame[source], errors="coerce")
        values[model_name] = series.iloc[
            int(model_nobs) : int(model_nobs) + total_steps
        ].to_numpy()
    return pd.DataFrame(values, index=index)


def serialise_frame(frame: pd.DataFrame | None) -> dict[str, Any] | None:
    """把外生变量表转换为稳定签名支持的基础类型。

    Parameters
    ----------
    frame : pandas.DataFrame or None
        需要纳入预测请求签名的未来外生变量表。

    Returns
    -------
    dict or None
        包含字符串列名和可 JSON 化单元格值的字典；输入为 ``None`` 时返回
        ``None``。
    """
    if frame is None:
        return None
    values = frame.astype(object).where(frame.notna(), None).values.tolist()
    return {
        "columns": [str(column) for column in frame.columns],
        "values": values,
    }


def actual_values_for_dates(
    dataset: Any,
    target: str | None,
    dates: Any,
) -> np.ndarray:
    """按预测结果日期对齐真实值，样本外未观测日期保留为空值。

    Parameters
    ----------
    dataset : OverviewDataset or None
        当前数据概览数据集。
    target : str or None
        目标变量列名。
    dates : sequence of datetime-like
        预测结果对应的日期序列。

    Returns
    -------
    numpy.ndarray
        与 ``dates`` 等长的浮点真实值数组；没有可用真实值的位置为 ``NaN``。
    """
    actual_dates, actual_values = _actual_values(dataset, target)
    result_dates = pd.DatetimeIndex(pd.to_datetime(dates))
    if actual_dates is None:
        return np.full(len(result_dates), np.nan)
    actual = pd.Series(actual_values, index=actual_dates)
    return actual.reindex(result_dates).to_numpy(dtype=float)


def _infer_calendar_offset(dataset: Any, model_dates: pd.DatetimeIndex):
    """从数据集或拟合日历推断追加未来日期所需的频率。"""
    candidates = []
    if dataset is not None:
        dates = dataset_time_index(dataset)
        if dates is not None:
            candidates.append(dates)
    candidates.append(model_dates)
    for dates in candidates:
        frequency = dates.freq or (
            pd.infer_freq(dates) if len(dates) >= 3 else None
        )
        if frequency is not None:
            return pd.tseries.frequencies.to_offset(frequency)
    raise ValueError("无法从日期数据推断频率，请补充至少 3 个规则间隔日期")


def _future_index(
    model_dates: pd.DatetimeIndex | None,
    total_steps: int,
    forecast_dates: pd.DatetimeIndex | None = None,
) -> pd.Index:
    """返回与 Ts 未来路径兼容的编辑器索引。"""
    dates = (
        forecast_dates
        if forecast_dates is not None
        else future_dates(model_dates, total_steps)
    )
    return dates if dates is not None else pd.RangeIndex(total_steps)


def _actual_values(
    dataset: Any,
    target: str | None,
) -> tuple[pd.DatetimeIndex, np.ndarray] | tuple[None, None]:
    """返回原始数据集中的真实值，保持日期和值的排序一致。"""
    if dataset is None or dataset.time_column is None or not target:
        return None, None
    frame = dataset.frame
    if target not in frame.columns:
        return None, None
    dates = pd.to_datetime(frame[dataset.time_column], errors="coerce")
    valid = dates.notna()
    actual_dates = pd.DatetimeIndex(dates.loc[valid])
    actual_values = pd.to_numeric(
        frame.loc[valid, target], errors="coerce"
    ).to_numpy(dtype=float)
    order = np.argsort(actual_dates.asi8)
    return actual_dates[order], actual_values[order]


__all__ = [
    "ForecastCalendar",
    "actual_values_for_dates",
    "build_forecast_calendar",
    "build_future_exog",
    "normalise_model_dates",
    "future_dates",
    "normalise_date_window",
    "resolve_prediction_positions",
    "serialise_frame",
]
