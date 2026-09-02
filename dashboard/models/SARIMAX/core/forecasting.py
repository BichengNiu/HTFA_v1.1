"""动态回归预测计算与统一预测表。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from dashboard.models.SARIMAX.core.forecast_planning import future_dates
from dashboard.models.SARIMAX.core.rdl_config import RDL_INTERVENTION_NAME


def produce_forecast(
    result: Any,
    start: int | str | pd.Timestamp,
    end: int | str | pd.Timestamp,
    alpha: float = 0.05,
    dynamic: bool = False,
    future_exog: pd.DataFrame | None = None,
    future_dates: pd.DatetimeIndex | None = None,
) -> dict[str, Any]:
    """对拟合结果预测，返回均值/区间/日期结构。

    Parameters
    ----------
    result : object
        已拟合的 Ts 模型结果。
    start : int or datetime-like
        预测起点；遵循 Ts ``predict`` 的位置/日期语义。
    end : int or datetime-like
        预测终点，包含该位置。
    alpha : float, default=0.05
        预测区间显著性水平。
    dynamic : bool, default=False
        传递给 Ts ``predict`` 的动态预测控制。
    future_exog : pandas.DataFrame or None, optional
        从拟合样本末期到 ``end`` 的完整未来外生变量路径。
    future_dates : pandas.DatetimeIndex or None, optional
        日期频率无法从拟合样本推断时使用的完整未来日期路径；直接传给 Ts。

    Returns
    -------
    dict[str, Any]
        包含预测数组、日期、窗口信息和 Ts 原始 prediction 对象的结构。
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha 必须在 (0, 1) 区间内")
    distributed_lags = getattr(result, "distributed_lags", None)
    if (
        getattr(result, "model_type", None) == "SARIMAX"
        and isinstance(distributed_lags, Mapping)
        and RDL_INTERVENTION_NAME in distributed_lags
    ):
        raise ValueError(
            "包含干预变量 I 的 RDL 目前仅支持历史干预分析，"
            "暂不支持样本内外预测"
        )

    predict_kwargs = {
        "start": start,
        "end": end,
        "dynamic": dynamic,
        "alpha": alpha,
        "future_exog": future_exog,
    }
    if future_dates is not None:
        predict_kwargs["future_dates"] = future_dates
    prediction = result.predict(**predict_kwargs)
    mean = np.asarray(prediction.mean, dtype=float)
    lower = np.asarray(prediction.lower, dtype=float)
    upper = np.asarray(prediction.upper, dtype=float)
    steps = len(mean)
    return {
        "mean": mean,
        "lower": lower,
        "upper": upper,
        "prediction": prediction,
        "future_dates": (
            None
            if future_dates is None
            else pd.DatetimeIndex(future_dates).copy()
        ),
        "dates": _prediction_dates(
            result,
            start,
            end,
            steps,
            supplied_future_dates=future_dates,
        ),
        "steps": steps,
        "start": start,
        "end": end,
        "alpha": alpha,
    }


def _prediction_dates(
    result: Any,
    start: int | str | pd.Timestamp | None,
    end: int | str | pd.Timestamp | None,
    length: int,
    supplied_future_dates: pd.DatetimeIndex | None = None,
) -> pd.DatetimeIndex | None:
    """按 Ts 预测窗口位置还原结果日期。"""
    dates = result.dates
    if dates is None:
        return None
    dates = pd.DatetimeIndex(dates)
    if isinstance(start, (int, np.integer)) and (
        end is None or isinstance(end, (int, np.integer))
    ):
        start_pos = int(start)
        end_pos = start_pos + length - 1 if end is None else int(end)
        if end_pos < len(dates):
            return dates[start_pos : end_pos + 1]
        future = (
            pd.DatetimeIndex(supplied_future_dates)
            if supplied_future_dates is not None
            else future_dates(dates, end_pos - len(dates) + 1)
        )
        if future is None:
            return None
        calendar = dates.append(future)
        return calendar[start_pos : end_pos + 1]

    if supplied_future_dates is not None:
        calendar = dates.append(pd.DatetimeIndex(supplied_future_dates))
        start_date = dates[0] if start is None else pd.Timestamp(start)
        end_date = dates[-1] if end is None else pd.Timestamp(end)
        selection = calendar[(calendar >= start_date) & (calendar <= end_date)]
        return pd.DatetimeIndex(selection[:length])

    frequency = dates.freq or pd.infer_freq(dates)
    if frequency is None:
        return None
    offset = pd.tseries.frequencies.to_offset(frequency)
    start_date = dates[0] if start is None else pd.Timestamp(start)
    end_date = (
        start_date + (length - 1) * offset
        if end is None
        else pd.Timestamp(end)
    )
    calendar = pd.date_range(
        start=dates[0],
        end=max(end_date, dates[-1]),
        freq=offset,
    )
    selection = calendar[(calendar >= start_date) & (calendar <= end_date)]
    return pd.DatetimeIndex(selection[:length])


def build_prediction_table(forecast: dict[str, Any]) -> pd.DataFrame:
    """把预测结构转换为可展示、可下载的表格。

    Parameters
    ----------
    forecast : dict[str, Any]
        ``produce_forecast`` 返回的预测结构。

    Returns
    -------
    pandas.DataFrame
        以日期或期数为索引的预测值、下界和上界表。
    """
    mean = np.asarray(forecast["mean"], dtype=float)
    lower = np.asarray(forecast["lower"], dtype=float)
    upper = np.asarray(forecast["upper"], dtype=float)
    dates = forecast.get("dates")
    if dates is not None:
        index = pd.DatetimeIndex(dates)
        index.name = "日期"
    else:
        start = forecast.get("start", 0)
        start = int(start) if isinstance(start, (int, np.integer)) else 0
        index = pd.RangeIndex(
            start + 1,
            start + len(mean) + 1,
            name="期数",
        )
    return pd.DataFrame(
        {
            "预测值": mean,
            "下界": lower,
            "上界": upper,
        },
        index=index,
    )


__all__ = ["build_prediction_table", "produce_forecast"]
