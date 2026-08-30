"""SARIMAX 工作流 - ③ 模型预测环节（预测区间与拟合/预测图）。"""

from __future__ import annotations

from datetime import date
import logging

import numpy as np
import pandas as pd

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from data_overview.core.dataset import numeric_variable_names
from dashboard.models.common.contracts import ForecastRequest, ForecastResult
from dashboard.models.common.ui.forecast_view import render_forecast_result
from dashboard.models.SARIMAX.core.data_loader import (
    dataset_time_index,
    forecast_sample_dates,
)
from dashboard.models.SARIMAX.core.modeling import (
    future_dates,
    translate_ts_error,
)
from dashboard.models.SARIMAX.core.adapters import (
    DynamicRegressionAdapter,
    best_result,
)
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.SARIMAX.ui.state import state

logger = logging.getLogger(__name__)
_MODEL_WORKFLOW = ModelWorkflow(DynamicRegressionAdapter())

MAX_FORECAST_EXTENSION = 12
_FORECAST_ALPHA_OPTIONS = (0.01, 0.05, 0.10)


def render_forecast_section(st_obj) -> None:
    """配置预测区间并生成统一的拟合值/预测值结果。"""
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成模型训练后可生成样本外预测。")
        return
    best = best_result(result)
    family = state.get("model_selection", ("SARIMAX", "手动配置"))[0]
    dataset = state.get("dataset")

    training_range = state.get("training_time_range")
    if not isinstance(training_range, (tuple, list)) or len(training_range) != 2:
        st_obj.error("未找到训练样本范围，请返回模型训练区设置日期滑轨。")
        return
    try:
        model_dates = _model_dates(best)
        base_calendar = _prediction_calendar(dataset, best, training_range[1])
        calendar = _extend_prediction_calendar(
            base_calendar,
            dataset,
            best,
            MAX_FORECAST_EXTENSION,
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
        st_obj.error(f"预测日期准备失败：{exc}")
        return
    if model_dates is None or len(model_dates) == 0:
        st_obj.error("当前模型没有有效日期索引，无法生成日期预测。")
        return
    if base_calendar is None or len(base_calendar) == 0:
        st_obj.error("当前数据集没有有效时间列，无法生成日期预测。")
        return

    model_nobs = int(best.nobs)
    if model_nobs != len(model_dates):
        st_obj.error("模型有效样本与日期索引长度不一致，无法安全生成预测。")
        return

    fit_signature = state.get("fit_signature")
    if state.get("forecast_widget_fit_signature") != fit_signature:
        st_obj.session_state.pop("sarimax_forecast_window", None)
        state.set("forecast_widget_fit_signature", fit_signature)

    date_options = tuple(pd.Timestamp(value).date() for value in calendar)
    training_end = pd.Timestamp(training_range[1])
    training_end_option = max(
        (value for value in date_options if value <= training_end.date()),
        default=date_options[min(model_nobs - 1, len(date_options) - 1)],
    )
    default_window = (date_options[0], training_end_option)
    existing_window = _normalise_date_window(
        st_obj.session_state.get("sarimax_forecast_window"),
        date_options,
    )
    if existing_window is None:
        st_obj.session_state.pop("sarimax_forecast_window", None)
        existing_window = default_window

    selected_window = st_obj.select_slider(
        "预测区间（训练内拟合；训练结束日后为预测）",
        options=date_options,
        value=existing_window,
        format_func=lambda value: value.isoformat(),
        key="sarimax_forecast_window",
        help=(
            "预测起点不得早于训练样本起点；预测区间进入训练结束日之后时，"
            "使用样本外预测。滑轨日期来自已预处理后的模型数据日历，"
            f"数据集末期后默认再提供 {MAX_FORECAST_EXTENSION} 期。"
        ),
    )

    control_columns = st_obj.columns([1, 4])
    with control_columns[0]:
        dynamic = st_obj.checkbox(
            "动态预测",
            key="sarimax_forecast_dynamic",
            help="传递给 Ts 的 dynamic 参数；样本外窗口本身已经采用递推。",
        )
    with control_columns[1]:
        show_confidence_interval = st_obj.checkbox(
            "置信区间",
            key="sarimax_forecast_ci",
            help="勾选后在预测图中显示浅灰色置信区间。",
        )
        alpha = st_obj.session_state.get("sarimax_forecast_alpha", 0.05)
        if alpha not in _FORECAST_ALPHA_OPTIONS:
            alpha = 0.05
        if show_confidence_interval:
            alpha = st_obj.radio(
                "区间值",
                options=_FORECAST_ALPHA_OPTIONS,
                index=1,
                format_func=lambda value: f"{1 - value:.0%}",
                horizontal=True,
                key="sarimax_forecast_alpha",
                help="选择预测区间的置信水平。",
            )

    try:
        start, end = _resolve_prediction_positions(
            calendar,
            selected_window,
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的日期边界
        st_obj.error(f"预测区间无效：{exc}")
        return

    selected_dates = calendar[start : end + 1]
    future_dates_for_model = (
        calendar[model_nobs : end + 1]
        if end >= model_nobs
        else None
    )
    total_steps = (
        len(future_dates_for_model) if future_dates_for_model is not None else 0
    )
    if end < start:
        st_obj.warning("预测终点不能早于预测起点。")
        return
    future_exog = None
    exog_names = tuple(best.exog_names)
    source_columns: tuple[str, ...] = ()
    if exog_names and future_dates_for_model is not None:
        future_exog, source_columns = _render_future_exog_editor(
            st_obj,
            dataset,
            best,
            total_steps,
            exog_names,
            future_dates_for_model,
        )

    signature = stable_signature(
        {
            "fit_signature": state.get("fit_signature"),
            "start": start,
            "end": end,
            "window": [str(value) for value in selected_window],
            "alpha": float(alpha),
            "dynamic": bool(dynamic),
            "source_columns": source_columns,
            "future_exog": _serialise_frame(future_exog),
        }
    )
    if st_obj.button(
        "生成预测",
        type="primary",
        key="sarimax_forecast_button",
        disabled=future_exog is not None and bool(future_exog.isna().any().any()),
    ):
        try:
            with st_obj.spinner("正在调用 Ts 包生成预测..."):
                forecast = _MODEL_WORKFLOW.forecast(
                    result,
                    ForecastRequest(
                        start=start,
                        end=end,
                        alpha=float(alpha),
                        dynamic=bool(dynamic),
                        future_exog=future_exog,
                        future_dates=future_dates_for_model,
                    ),
                )
        except Exception as exc:
            st_obj.error(translate_ts_error(exc))
            logger.exception("SARIMAX 预测失败")
            return
        state.set("forecast", forecast)
        state.set("forecast_signature", signature)

    forecast = state.get("forecast")
    if forecast is None or state.get("forecast_signature") != signature:
        return

    target = state.get("target_variable")
    actual_values = (
        _actual_values_for_dates(dataset, target, forecast.dates)
        if forecast.dates is not None
        else None
    )
    caption = (
        "训练样本区间："
        f"{model_dates[0].date().isoformat()} 至 "
        f"{training_end_option.isoformat()}；当前预测区间："
        f"{selected_dates[0].date().isoformat()} 至 "
        f"{selected_dates[-1].date().isoformat()}，共 {len(selected_dates)} 期，"
        f"其中样本外 {max(0, end - model_nobs + 1)} 期；"
        f"数据集末期后最多延伸 {MAX_FORECAST_EXTENSION} 期。"
    )

    def render_chart(st_instance, forecast_result, *, target, show_confidence_interval):
        _render_forecast_chart(
            st_instance,
            best,
            forecast_result,
            target=target,
            show_confidence_interval=show_confidence_interval,
        )

    render_forecast_result(
        st_obj,
        forecast,
        actual_values=actual_values,
        target=target,
        caption=caption,
        download_name=f"{family}_预测_{int(forecast.steps)}期.csv",
        chart_renderer=render_chart,
        show_confidence_interval=show_confidence_interval,
        download_key="sarimax_forecast_download",
    )


def _model_dates(best) -> pd.DatetimeIndex | None:
    """返回拟合结果的有效日期索引。"""
    dates = getattr(best, "dates", None)
    if dates is None:
        return None
    return pd.DatetimeIndex(pd.to_datetime(dates)).drop_duplicates()


def _prediction_calendar(
    dataset,
    best,
    training_end: pd.Timestamp,
) -> pd.DatetimeIndex:
    """拼接模型训练日历与当前数据集已有的样本外日历。"""
    model_dates = _model_dates(best)
    if model_dates is None:
        raise ValueError("模型没有有效日期索引")
    observed_future = forecast_sample_dates(dataset, training_end)
    calendar = model_dates
    if observed_future is not None and len(observed_future):
        calendar = calendar.append(pd.DatetimeIndex(observed_future))
    return calendar.sort_values().drop_duplicates()


def _normalise_date_window(value, options: tuple[date, ...]):
    """校验 Streamlit 日期滑轨的已有值是否仍属于当前日历。"""
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        window = tuple(pd.Timestamp(item).date() for item in value)
    except (TypeError, ValueError):
        return None
    if window[0] > window[1] or any(item not in options for item in window):
        return None
    return window


def _infer_calendar_offset(dataset, best):
    """从原始数据或拟合日历中推断追加样本外期数所需的频率。"""
    candidates = []
    if dataset is not None:
        dates = dataset_time_index(dataset)
        if dates is not None:
            candidates.append(dates)
    model_dates = _model_dates(best)
    if model_dates is not None:
        candidates.append(model_dates)
    for dates in candidates:
        frequency = dates.freq or (pd.infer_freq(dates) if len(dates) >= 3 else None)
        if frequency is not None:
            return pd.tseries.frequencies.to_offset(frequency)
    raise ValueError("无法从日期数据推断频率，请补充至少 3 个规则间隔日期")


def _extend_prediction_calendar(base_calendar, dataset, best, periods):
    """在当前日期日历末端追加有限的未来日期。"""
    calendar = pd.DatetimeIndex(base_calendar).sort_values().drop_duplicates()
    if periods <= 0:
        return calendar
    offset = _infer_calendar_offset(dataset, best)
    extension = pd.date_range(
        start=calendar[-1] + offset,
        periods=int(periods),
        freq=offset,
    )
    return calendar.append(extension)


def _resolve_prediction_positions(
    calendar: pd.DatetimeIndex,
    selected_window,
) -> tuple[int, int]:
    """把日期滑轨转换成 Ts 的闭区间位置。"""
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


def _render_future_exog_editor(
    st_obj,
    dataset,
    best,
    total_steps: int,
    exog_names: tuple[str, ...],
    forecast_dates: pd.DatetimeIndex | None = None,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """从数据集预填未来外生路径，并允许用户选择来源列及编辑数值。"""
    numeric = [] if dataset is None else numeric_variable_names(dataset.frame)
    if not numeric:
        st_obj.error("当前数据表没有可用的数值列，无法提供未来外生变量路径。")
        empty = pd.DataFrame(
            np.nan,
            index=_future_index(best, total_steps, forecast_dates),
            columns=exog_names,
        )
        return empty, ()
    source_columns = []
    for position, model_name in enumerate(exog_names):
        default = (
            model_name
            if model_name in numeric
            else (numeric[0] if numeric else None)
        )
        selected = st_obj.selectbox(
            f"{model_name} 的未来值来源",
            options=numeric,
            index=numeric.index(default) if default in numeric else 0,
            key=f"sarimax_future_exog_source_{position}",
            help="从当前数据表选择该模型外生变量的未来路径。",
        )
        source_columns.append(selected)
    source_columns = tuple(source_columns)
    if not source_columns:
        empty = pd.DataFrame(
            np.nan,
            index=_future_index(best, total_steps, forecast_dates),
            columns=exog_names,
        )
        return empty, source_columns

    editor_frame = _future_exog_from_dataset(
        dataset,
        best,
        total_steps,
        source_columns,
        exog_names,
        forecast_dates,
    )
    editor_signature = stable_signature(
        {
            "start": int(best.nobs),
            "steps": total_steps,
            "sources": source_columns,
            "index": [str(value) for value in editor_frame.index],
        }
    )
    if state.get("future_exog_editor_signature") != editor_signature:
        st_obj.session_state.pop("sarimax_future_exog_editor", None)
        state.set("future_exog_editor_signature", editor_signature)
    st_obj.markdown("**未来外生变量路径**")
    st_obj.caption("默认从当前数据表提取；空值可直接在下表补录。")
    edited = st_obj.data_editor(
        editor_frame,
        key="sarimax_future_exog_editor",
        num_rows="fixed",
    )
    return edited.astype(float), source_columns


def _future_exog_from_dataset(
    dataset,
    best,
    total_steps: int,
    source_columns: tuple[str, ...],
    exog_names: tuple[str, ...],
    forecast_dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """按拟合结果的未来日历从当前数据框提取外生变量路径。"""
    if dataset is None:
        return pd.DataFrame(
            np.nan,
            index=_future_index(best, total_steps, forecast_dates),
            columns=exog_names,
        )
    frame = dataset.frame.copy()
    if dataset.time_column is not None:
        dates = pd.DatetimeIndex(pd.to_datetime(frame[dataset.time_column]))
        frame = frame.drop(columns=[dataset.time_column])
        frame.index = dates
        frame = frame.sort_index()
        index = (
            forecast_dates
            if forecast_dates is not None
            else future_dates(best, total_steps, fallback_dates=dates)
        )
        if index is None:
            index = pd.RangeIndex(total_steps)
        values = {
            model_name: pd.to_numeric(frame[source], errors="coerce").reindex(index)
            for model_name, source in zip(exog_names, source_columns)
        }
        return pd.DataFrame(values, index=index)

    index = _future_index(best, total_steps, forecast_dates)
    values = {}
    for model_name, source in zip(exog_names, source_columns):
        series = pd.to_numeric(frame[source], errors="coerce")
        values[model_name] = series.iloc[
            int(best.nobs) : int(best.nobs) + total_steps
        ].to_numpy()
    return pd.DataFrame(values, index=index)


def _future_index(
    best,
    total_steps: int,
    forecast_dates: pd.DatetimeIndex | None = None,
) -> pd.Index:
    """返回与 Ts 未来路径兼容的编辑器索引。"""
    dates = (
        forecast_dates
        if forecast_dates is not None
        else future_dates(best, total_steps)
    )
    return dates if dates is not None else pd.RangeIndex(total_steps)


def _serialise_frame(frame: pd.DataFrame | None):
    """把外生变量表转换为稳定签名支持的基础类型。"""
    if frame is None:
        return None
    values = frame.astype(object).where(frame.notna(), None).values.tolist()
    return {"columns": [str(column) for column in frame.columns], "values": values}


def _actual_values(dataset, target: str | None):
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


def _actual_values_for_dates(dataset, target: str | None, dates) -> np.ndarray:
    """按预测结果日期对齐真实值，样本外未观测日期保留为空值。"""
    actual_dates, actual_values = _actual_values(dataset, target)
    result_dates = pd.DatetimeIndex(pd.to_datetime(dates))
    if actual_dates is None:
        return np.full(len(result_dates), np.nan)
    actual = pd.Series(actual_values, index=actual_dates)
    return actual.reindex(result_dates).to_numpy(dtype=float)


def _date_numbers(values) -> np.ndarray:
    """把日期转换成 Matplotlib 日期数值，避免字符串转换兼容性问题。"""
    import matplotlib.dates as mdates

    dates = pd.DatetimeIndex(pd.to_datetime(values))
    return np.asarray(mdates.date2num(dates.to_pydatetime()), dtype=float)


def _remap_prediction_lines(axis, calendar: pd.DatetimeIndex):
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


def _render_forecast_chart(
    st_obj,
    best,
    forecast: ForecastResult,
    *,
    target: str | None,
    show_confidence_interval: bool = False,
) -> None:
    """复用 Ts 默认预测图并将横轴转换为真实日期。"""
    try:
        import matplotlib.dates as mdates

        with matplotlib_date_compatibility():
            prediction = forecast.prediction
            prediction_dates = forecast.dates
            if prediction_dates is None:
                raise ValueError("无日期模型不能绘制日期预测图")
            calendar = _model_dates(best)
            if calendar is None:
                raise ValueError("模型没有有效日期索引")
            calendar = calendar.append(prediction_dates).drop_duplicates().sort_values()
            prediction_positions = calendar.get_indexer(prediction_dates)
            if np.any(prediction_positions < 0):
                raise ValueError("预测结果日期不在当前模型日历中")
            figure, axis = prediction.plot(
                ci=show_confidence_interval,
                xlim=(
                    int(prediction_positions[0]),
                    int(prediction_positions[-1]),
                )
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


__all__ = ["render_forecast_section"]
