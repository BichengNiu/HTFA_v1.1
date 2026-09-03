"""SARIMAX 预测图的 Streamlit 适配器。

Ts 负责生成预测图的内容和默认样式，本模块只把位置横轴转换为真实日期，
并交给 HTFA 的统一图表渲染器显示。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from Ts.TsPlots import plot_series

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.models.common.contracts import ForecastResult
from dashboard.models.SARIMAX.core.forecast_planning import normalise_model_dates

logger = logging.getLogger(__name__)


def render_forecast_chart(
    st_obj,
    model_dates,
    forecast: ForecastResult,
    *,
    target: str | None,
    show_confidence_interval: bool = False,
) -> None:
    """复用 Ts 默认预测图并将横轴转换为真实日期。

    Parameters
    ----------
    st_obj : object
        提供 ``warning`` 方法的 Streamlit 页面对象。
    model_dates : sequence of datetime-like or None
        模型适配器提供的有效样本日期。
    forecast : ForecastResult
        已生成的预测结果及其对应日期。
    target : str or None
        目标变量名，用作纵轴标签。
    show_confidence_interval : bool, default=False
        是否请求 Ts 绘制预测置信区间。
    """
    try:
        import matplotlib.dates as mdates

        with matplotlib_date_compatibility():
            prediction = forecast.prediction
            prediction_dates = forecast.dates
            if prediction_dates is None:
                raise ValueError("无日期模型不能绘制日期预测图")
            model_dates = normalise_model_dates(model_dates)
            if model_dates is None:
                raise ValueError("模型没有有效日期索引")
            calendar = (
                model_dates.append(prediction_dates)
                .drop_duplicates()
                .sort_values()
            )
            prediction_positions = calendar.get_indexer(prediction_dates)
            if np.any(prediction_positions < 0):
                raise ValueError("预测结果日期不在当前模型日历中")
            figure, axis = prediction.plot(
                ci=show_confidence_interval,
                xlim=(
                    int(prediction_positions[0]),
                    int(prediction_positions[-1]),
                ),
            )
            _remap_prediction_lines(axis, calendar)
            _apply_forecast_axis_labels(axis, target)

            x_start, x_end = _date_numbers(
                [prediction_dates[0], prediction_dates[-1]]
            )
            if x_start == x_end:
                x_start -= 0.5
                x_end += 0.5
            axis.set_xlim(x_start, x_end)
            locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
            axis.xaxis.set_major_locator(locator)
            axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            render_pyplot_figure(
                st_obj,
                figure,
                place_legend_bottom=False,
            )
    except Exception as exc:
        st_obj.warning(f"预测图无法绘制：{exc}")
        logger.warning("SARIMAX 预测图绘制失败", exc_info=True)


def render_forecast_error_chart(st_obj, detail: pd.DataFrame) -> None:
    """通过 Ts 的统一序列绘图接口展示预测误差。

    Parameters
    ----------
    st_obj : object
        提供 ``warning`` 方法的 Streamlit 页面对象。
    detail : pandas.DataFrame
        至少包含“日期”和“误差”列的逐点评估明细。
    """
    try:
        dates = pd.DatetimeIndex(pd.to_datetime(detail["日期"]))
        errors = pd.to_numeric(detail["误差"], errors="coerce")
        error_series = pd.Series(
            errors.to_numpy(dtype=float),
            index=dates,
            name="预测误差",
        )
        if not np.isfinite(error_series.to_numpy()).any():
            return
        with matplotlib_date_compatibility():
            figure, _axis = plot_series(
                error_series,
                facet=False,
                auto_dual_y=False,
                title="预测误差",
                xtitle="",
                ytitle="预测误差",
                show_legend=False,
            )
            render_pyplot_figure(
                st_obj,
                figure,
                place_legend_bottom=False,
            )
    except Exception as exc:
        st_obj.warning(f"预测误差图无法绘制：{exc}")
        logger.warning("SARIMAX 预测误差图绘制失败", exc_info=True)


def _date_numbers(values) -> np.ndarray:
    """把日期转换成 Matplotlib 日期数值，避免字符串转换兼容性问题。"""
    import matplotlib.dates as mdates

    dates = pd.DatetimeIndex(pd.to_datetime(values))
    return np.asarray(mdates.date2num(dates.to_pydatetime()), dtype=float)


def _remap_prediction_lines(axis, calendar: pd.DatetimeIndex) -> None:
    """把 Ts 预测图的折线和区间面片横轴转换为真实日期横轴。"""
    calendar_numbers = _date_numbers(calendar)
    for line in axis.lines:
        positions = np.rint(np.asarray(line.get_xdata(), dtype=float)).astype(int)
        if np.all((positions >= 0) & (positions < len(calendar_numbers))):
            line.set_xdata(calendar_numbers[positions])
    for collection in axis.collections:
        for path in collection.get_paths():
            vertices = np.asarray(path.vertices, dtype=float)
            if vertices.ndim != 2 or vertices.shape[1] < 2:
                continue
            if not np.all(np.isfinite(vertices[:, 0])):
                continue
            positions = np.rint(vertices[:, 0]).astype(int)
            if np.all(
                np.isfinite(vertices[:, 0])
                & (positions >= 0)
                & (positions < len(calendar_numbers))
            ):
                vertices[:, 0] = calendar_numbers[positions]


def _apply_forecast_axis_labels(axis, target: str | None) -> None:
    """把预测图标签改为模型目标变量，并隐藏横轴与主标题。"""
    axis.set_title("")
    axis.set_xlabel("")
    axis.set_ylabel(str(target) if target else "Value")


__all__ = ["render_forecast_chart", "render_forecast_error_chart"]
