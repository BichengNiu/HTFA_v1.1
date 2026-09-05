"""SARIMAX 工作流 - ③ 模型预测环节（预测区间与拟合/预测图）。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from htfa.workspace import stable_signature
from htfa.data.tabular import numeric_variable_names
from htfa.models.univariate.common.contracts import ForecastRequest
from htfa.models.univariate.common.forecast_evaluation import (
    ForecastAccuracyReport,
    build_accuracy_workbook,
    evaluate_current_forecast,
    evaluate_fixed_holdout,
    evaluate_in_sample_fit,
    evaluate_rolling_forecast,
    evaluate_training_rolling,
)
from htfa.models.univariate.common.ui.forecast_view import render_forecast_result
from htfa.models.univariate.sarimax.core.forecast_planning import (
    actual_values_for_dates,
    build_forecast_calendar,
    build_future_exog,
    normalise_date_window,
    resolve_prediction_positions,
    serialise_frame,
)
from htfa.models.univariate.sarimax.core.data_loader import (
    dataset_time_index,
    prepare_modeling_inputs,
)
from htfa.models.univariate.sarimax.core.modeling import (
    MAX_ROLLING_ORIGINS,
    evaluation_seasonal_period,
    run_fixed_holdout_evaluation,
    run_historical_rolling_evaluation,
    run_training_rolling_evaluation,
    translate_ts_error,
)
from htfa.models.univariate.sarimax.core.adapters import DynamicRegressionAdapter
from htfa.models.univariate.common.workflow import ModelWorkflow
from htfa.models.univariate.sarimax.ui.pages.sections.forecast_chart import (
    render_forecast_chart,
    render_forecast_error_chart,
)
from htfa.models.univariate.sarimax.ui.state import ModelPageScope, SARIMAX_SCOPE

logger = logging.getLogger(__name__)
_MODEL_WORKFLOW = ModelWorkflow(DynamicRegressionAdapter())

MAX_FORECAST_EXTENSION = 12
_FORECAST_ALPHA_OPTIONS = (0.01, 0.05, 0.10)


def render_forecast_section(st_obj, scope: ModelPageScope = SARIMAX_SCOPE) -> None:
    """配置预测区间并生成统一的拟合值/预测值结果。"""
    state = scope.state
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成模型训练后可生成样本外预测。")
        return
    intervention_only = (
        scope.family == "RDL" and state.get("intervention_config") is not None
    )
    if intervention_only:
        st_obj.info(
            "当前 RDL 干预分析仅支持历史训练样本；"
            "包含干预变量 I 的样本外预测场景暂未开放。"
        )
        training_range = state.get("training_time_range")
        if isinstance(training_range, (tuple, list)) and len(training_range) == 2:
            _render_forecast_evaluation(
                st_obj,
                scope,
                result,
                state.get("dataset"),
                pd.Timestamp(training_range[1]),
            )
        return
    st_obj.markdown("**预测结果**")
    try:
        forecast_context = _MODEL_WORKFLOW.forecast_context(result)
    except Exception as exc:  # noqa: BLE001 - 用户可读的模型上下文边界
        st_obj.error(f"预测模型上下文准备失败：{exc}")
        return
    family = scope.family
    dataset = state.get("dataset")

    training_range = state.get("training_time_range")
    if not isinstance(training_range, (tuple, list)) or len(training_range) != 2:
        st_obj.error("未找到训练样本范围，请返回模型训练区设置日期滑轨。")
        return
    try:
        forecast_calendar = build_forecast_calendar(
            dataset,
            forecast_context.model_dates,
            training_range[1],
            extension_periods=MAX_FORECAST_EXTENSION,
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
        st_obj.error(f"预测日期准备失败：{exc}")
        return
    model_dates = forecast_calendar.model_dates
    base_calendar = forecast_calendar.base_dates
    calendar = forecast_calendar.dates
    if model_dates is None or len(model_dates) == 0:
        st_obj.error("当前模型没有有效日期索引，无法生成日期预测。")
        return
    if base_calendar is None or len(base_calendar) == 0:
        st_obj.error("当前数据集没有有效时间列，无法生成日期预测。")
        return

    model_nobs = forecast_context.model_nobs
    if model_nobs != len(model_dates):
        st_obj.error("模型有效样本与日期索引长度不一致，无法安全生成预测。")
        return
    minimum_prediction_start = forecast_context.minimum_prediction_start
    if minimum_prediction_start >= model_nobs:
        st_obj.error("模型没有可用于预测的有效样本区间。")
        return

    fit_signature = state.get("fit_signature")
    if state.get("forecast_widget_fit_signature") != fit_signature:
        st_obj.session_state.pop(scope.key("forecast_window"), None)
        state.set("forecast_widget_fit_signature", fit_signature)

    date_options = tuple(pd.Timestamp(value).date() for value in calendar)
    training_end = pd.Timestamp(training_range[1])
    training_end_option = max(
        (value for value in date_options if value <= training_end.date()),
        default=date_options[min(model_nobs - 1, len(date_options) - 1)],
    )
    available_date_options = date_options[minimum_prediction_start:]
    available_training_end = max(
        (
            value
            for value in available_date_options
            if value <= training_end.date()
        ),
        default=available_date_options[0],
    )
    default_window = (available_date_options[0], available_training_end)
    existing_window = normalise_date_window(
        st_obj.session_state.get(scope.key("forecast_window")),
        available_date_options,
    )
    if existing_window is None:
        st_obj.session_state.pop(scope.key("forecast_window"), None)
        existing_window = default_window

    selected_window = st_obj.select_slider(
        "预测区间（训练内拟合；训练结束日后为预测）",
        options=available_date_options,
        value=existing_window,
        format_func=lambda value: value.isoformat(),
        key=scope.key("forecast_window"),
        help=(
            "预测起点从状态空间初始化期之后开始；预测区间进入训练结束日之后时，"
            "使用样本外预测。滑轨日期来自已预处理后的模型数据日历，"
            f"数据集末期后默认再提供 {MAX_FORECAST_EXTENSION} 期。"
        ),
    )
    if minimum_prediction_start > 0:
        st_obj.caption(
            "已跳过状态空间初始化期的 "
            f"{minimum_prediction_start} 期，避免无效的初始预测值。"
        )

    control_columns = st_obj.columns([1, 4])
    with control_columns[0]:
        dynamic = st_obj.checkbox(
            "动态预测",
            key=scope.key("forecast_dynamic"),
            help="传递给 Ts 的 dynamic 参数；样本外窗口本身已经采用递推。",
        )
    with control_columns[1]:
        show_confidence_interval = st_obj.checkbox(
            "置信区间",
            key=scope.key("forecast_ci"),
            help="勾选后在预测图中显示浅灰色置信区间。",
        )
        alpha = st_obj.session_state.get(scope.key("forecast_alpha"), 0.05)
        if alpha not in _FORECAST_ALPHA_OPTIONS:
            alpha = 0.05
        if show_confidence_interval:
            alpha = st_obj.radio(
                "区间值",
                options=_FORECAST_ALPHA_OPTIONS,
                index=1,
                format_func=lambda value: f"{1 - value:.0%}",
                horizontal=True,
                key=scope.key("forecast_alpha"),
                help="选择预测区间的置信水平。",
            )

    try:
        start, end = resolve_prediction_positions(
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
    exog_names = forecast_context.exog_names
    source_columns: tuple[str, ...] = ()
    if exog_names and future_dates_for_model is not None:
        future_exog, source_columns = _render_future_exog_editor(
            st_obj,
            dataset,
            model_nobs,
            forecast_context.model_dates,
            total_steps,
            exog_names,
            future_dates_for_model,
            scope,
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
            "future_exog": serialise_frame(future_exog),
        }
    )
    if st_obj.button(
        "生成预测",
        type="primary",
        key=scope.key("forecast_button"),
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
        scope.store_downstream_result(
            "forecast",
            forecast,
            "forecast_signature",
            signature,
        )

    forecast = state.get("forecast")
    if forecast is None or state.get("forecast_signature") != signature:
        return

    target = state.get("target_variable")
    actual_values = (
        actual_values_for_dates(dataset, target, forecast.dates)
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
        render_forecast_chart(
            st_instance,
            forecast_context.model_dates,
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
        download_key=scope.key("forecast_download"),
    )
    _render_forecast_evaluation(
        st_obj,
        scope,
        result,
        dataset,
        training_end,
    )


def _render_forecast_evaluation(
    st_obj,
    scope: ModelPageScope,
    result,
    dataset,
    training_end: pd.Timestamp,
) -> None:
    """展示训练期评估和样本外评估两个独立 Tab。"""
    st_obj.markdown("**预测精度评估**")
    training_tab, oos_tab = st_obj.tabs(["训练期评估", "样本外评估"])
    with training_tab:
        _render_training_evaluation(
            st_obj,
            scope,
            result,
            dataset,
            training_end,
        )
    with oos_tab:
        _render_oos_evaluation(
            st_obj,
            scope,
            result,
            dataset,
            training_end,
        )


def _render_training_evaluation(
    st_obj,
    scope: ModelPageScope,
    result,
    dataset,
    training_end: pd.Timestamp,
) -> None:
    """展示完整训练期拟合和训练期 H 期滚动评估。"""
    state = scope.state
    config = state.get("fit_config")
    if config is None:
        st_obj.info("当前拟合结果缺少配置快照，请重新拟合模型后进行评估。")
        return
    try:
        full_series, full_exog, full_dates, training_position = (
            _evaluation_inputs(state, dataset)
        )
        training_series = full_series.iloc[:training_position]
        training_exog = (
            None
            if full_exog is None
            else full_exog.iloc[:training_position]
        )
        context = _MODEL_WORKFLOW.forecast_context(result)
        fitted = _MODEL_WORKFLOW.fitted_values(result)
        if len(training_series) != context.model_nobs:
            raise ValueError(
                "训练期处理后样本数与模型有效样本数不一致，"
                f"{len(training_series)} != {context.model_nobs}"
            )
        accuracy = evaluate_in_sample_fit(
            training_series.to_numpy(dtype=float),
            fitted,
            full_dates[:training_position],
            seasonal_period=evaluation_seasonal_period(config, result),
        )
    except Exception as exc:  # noqa: BLE001 - 评估不应阻断预测结果
        st_obj.warning(f"训练期评估暂不可用：{translate_ts_error(exc)}")
        return

    st_obj.markdown("**完整训练期窗口**")
    st_obj.caption(
        f"训练窗口：{full_dates[0].date().isoformat()} 至 "
        f"{training_end.date().isoformat()}；使用一次拟合结果的拟合值。"
    )
    _render_accuracy_report(
        st_obj,
        accuracy,
        download_key=scope.key("forecast_training_download"),
        download_name=f"{scope.family}_训练期完整窗口.xlsx",
    )

    horizon = st_obj.number_input(
        "训练期滚动预测期数 H",
        min_value=1,
        max_value=12,
        value=1,
        step=1,
        key=scope.key("forecast_training_horizon"),
        help="训练集内部伪样本外验证；窗口采用扩展方式，step 固定为 1。",
    )
    st_obj.caption(
        "训练期滚动采用扩展窗口、step=1；初始训练样本数为 max(10, 2H)，"
        f"最多评估最近 {MAX_ROLLING_ORIGINS} 个连续滚动窗口；"
        "自动 SARIMAX 固定当前选中的阶数，不在每个窗口重新选阶。"
    )
    if st_obj.button(
        "滚动验证",
        key=scope.key("forecast_training_button"),
        type="primary",
    ):
        signature = stable_signature(
            {
                "fit_signature": state.get("fit_signature"),
                "target": state.get("target_variable"),
                "horizon": int(horizon),
            }
        )
        try:
            with st_obj.spinner("正在执行滚动验证，请稍候..."):
                comparison = run_training_rolling_evaluation(
                    training_series,
                    training_exog,
                    config,
                    result,
                    horizon=int(horizon),
                )
                result_name = next(iter(comparison.results))
                evaluation_result = comparison.results[result_name]
                rolling_accuracy = evaluate_training_rolling(
                    evaluation_result.actual,
                    evaluation_result.mean,
                    evaluation_result.splits,
                    training_series.to_numpy(dtype=float),
                    full_dates[:training_position],
                    horizon=int(horizon),
                    seasonal_period=evaluation_seasonal_period(config, result),
                )
            payload = {
                "complete": accuracy,
                "rolling": rolling_accuracy,
                "failures": tuple(evaluation_result.failures),
                "n_splits": len(evaluation_result.splits),
            }
            scope.store_downstream_result(
                "training_evaluation",
                payload,
                "training_evaluation_signature",
                signature,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的回测边界
            st_obj.error(f"训练期滚动验证失败：{translate_ts_error(exc)}")
            logger.exception("%s 训练期滚动验证失败", scope.family)
            return

    signature = stable_signature(
        {
            "fit_signature": state.get("fit_signature"),
            "target": state.get("target_variable"),
            "horizon": int(horizon),
        }
    )
    payload = state.get("training_evaluation")
    if (
        not isinstance(payload, dict)
        or state.get("training_evaluation_signature") != signature
    ):
        return
    accuracy = payload.get("rolling")
    if not isinstance(accuracy, ForecastAccuracyReport):
        return
    if payload.get("failures"):
        st_obj.warning(
            f"有 {len(payload['failures'])} 个滚动窗口拟合失败，"
            "这些窗口已从指标覆盖范围中保留为无效值。"
        )
    st_obj.markdown("**训练期 H 期滚动窗口**")
    st_obj.caption(
        f"初始训练样本数至少为 max(10, 2H)；最多保留最近 "
        f"{MAX_ROLLING_ORIGINS} 个窗口，共完成 {payload.get('n_splits', 0)} 个滚动窗口。"
    )
    _render_accuracy_report(
        st_obj,
        accuracy,
        download_key=scope.key("forecast_training_rolling_download"),
        download_name=f"{scope.family}_训练期H期滚动.xlsx",
    )


def _render_oos_evaluation(
    st_obj,
    scope: ModelPageScope,
    result,
    dataset,
    training_end: pd.Timestamp,
) -> None:
    """展示完整样本外验证和样本外 H 期滚动回测。"""
    state = scope.state
    config = state.get("fit_config")
    if config is None:
        st_obj.info("当前拟合结果缺少配置快照，请重新拟合模型后进行评估。")
        return
    if (
        scope.family == "RDL"
        and state.get("intervention_config") is not None
    ):
        st_obj.info("当前干预分析不支持样本外评估。")
        return
    try:
        full_series, full_exog, full_dates, training_position = (
            _evaluation_inputs(state, dataset)
        )
        oos_dates = full_dates[training_position:]
        if not len(oos_dates):
            st_obj.info("训练结束日之后没有可评分的真实观测。")
            return
        context = _MODEL_WORKFLOW.forecast_context(result)
        if context.model_nobs != training_position:
            raise ValueError(
                "训练期处理后样本数与模型有效样本数不一致，"
                f"{training_position} != {context.model_nobs}"
            )
        future_exog = (
            None
            if full_exog is None
            else full_exog.iloc[training_position:]
        )
        fixed = run_fixed_holdout_evaluation(
            result,
            start=training_position,
            end=training_position + len(oos_dates) - 1,
            future_exog=future_exog,
            future_dates=oos_dates,
        )
        accuracy = evaluate_fixed_holdout(
            full_series.iloc[training_position:].to_numpy(dtype=float),
            fixed["mean"],
            oos_dates,
            full_series.to_numpy(dtype=float),
            full_dates,
            training_end,
            seasonal_period=evaluation_seasonal_period(config, result),
        )
    except Exception as exc:  # noqa: BLE001 - 评估不应阻断预测结果
        st_obj.warning(f"样本外评估暂不可用：{translate_ts_error(exc)}")
        return

    st_obj.markdown("**完整样本外窗口**")
    st_obj.caption(
        f"验证窗口：{oos_dates[0].date().isoformat()} 至 "
        f"{oos_dates[-1].date().isoformat()}；固定训练结束日一次拟合，"
        "不在验证窗口内重新拟合。"
    )
    _render_accuracy_report(
        st_obj,
        accuracy,
        download_key=scope.key("forecast_oos_download"),
        download_name=f"{scope.family}_样本外完整窗口.xlsx",
    )

    horizon = st_obj.number_input(
        "样本外滚动预测期数 H",
        min_value=1,
        max_value=12,
        value=1,
        step=1,
        key=scope.key("forecast_oos_horizon"),
        help="训练结束日后按扩展窗口逐期前推，并在每个起点重新拟合。",
    )
    st_obj.caption(
        "样本外滚动采用扩展窗口、step=1；初始训练窗口固定到训练结束日，"
        f"最多评估最近 {MAX_ROLLING_ORIGINS} 个连续滚动窗口；"
        "仅使用数据中已有真实值的日期，含外生变量时使用观测到的未来路径。"
    )
    if st_obj.button(
        "滚动验证",
        key=scope.key("forecast_oos_button"),
        type="primary",
    ):
        signature = stable_signature(
            {
                "fit_signature": state.get("fit_signature"),
                "target": state.get("target_variable"),
                "horizon": int(horizon),
            }
        )
        try:
            with st_obj.spinner("正在执行滚动验证，请稍候..."):
                comparison = run_historical_rolling_evaluation(
                    full_series,
                    full_exog,
                    config,
                    result,
                    initial_window=training_position,
                    horizon=int(horizon),
                )
                result_name = next(iter(comparison.results))
                evaluation_result = comparison.results[result_name]
                rolling_accuracy = evaluate_rolling_forecast(
                    evaluation_result.actual,
                    evaluation_result.mean,
                    evaluation_result.splits,
                    full_series.to_numpy(dtype=float),
                    full_dates,
                    seasonal_period=evaluation_seasonal_period(config, result),
                )
            payload = {
                "complete": accuracy,
                "rolling": rolling_accuracy,
                "failures": tuple(evaluation_result.failures),
                "n_splits": len(evaluation_result.splits),
            }
            scope.store_downstream_result(
                "oos_evaluation",
                payload,
                "oos_evaluation_signature",
                signature,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的回测边界
            st_obj.error(f"样本外滚动回测失败：{translate_ts_error(exc)}")
            logger.exception("%s 样本外滚动回测失败", scope.family)
            return

    signature = stable_signature(
        {
            "fit_signature": state.get("fit_signature"),
            "target": state.get("target_variable"),
            "horizon": int(horizon),
        }
    )
    payload = state.get("oos_evaluation")
    if (
        not isinstance(payload, dict)
        or state.get("oos_evaluation_signature") != signature
    ):
        return
    accuracy = payload.get("rolling")
    if not isinstance(accuracy, ForecastAccuracyReport):
        return
    if payload.get("failures"):
        st_obj.warning(
            f"有 {len(payload['failures'])} 个滚动窗口拟合失败，"
            "这些窗口已从指标覆盖范围中保留为无效值。"
        )
    st_obj.markdown("**样本外 H 期滚动窗口**")
    st_obj.caption(
        f"初始训练窗口固定到训练结束日；最多保留最近 {MAX_ROLLING_ORIGINS} 个窗口，"
        f"共完成 {payload.get('n_splits', 0)} 个滚动窗口。"
    )
    _render_accuracy_report(
        st_obj,
        accuracy,
        download_key=scope.key("forecast_oos_rolling_download"),
        download_name=f"{scope.family}_样本外H期滚动.xlsx",
    )


def _evaluation_inputs(state, dataset):
    """重建训练期和样本外评估共用的、无缺失处理后输入。"""
    training_range = state.get("training_time_range")
    target = state.get("target_variable")
    exog_names = tuple(state.get("exog_variables") or ())
    if dataset is None or not target:
        raise ValueError("缺少评估数据或目标变量")
    full_dates = dataset_time_index(dataset)
    if full_dates is None or len(full_dates) == 0:
        raise ValueError("预测评估需要日期索引")
    if not isinstance(training_range, (tuple, list)) or len(training_range) != 2:
        raise ValueError("缺少有效的训练样本范围")
    series, exog, index = prepare_modeling_inputs(
        dataset,
        target,
        exog_names,
        time_range=(pd.Timestamp(training_range[0]), full_dates[-1]),
        preprocessing=tuple(state.get("data_preprocessing") or ()),
        missing_value_method=state.get("missing_value_method", "无"),
    )
    valid = series.notna().to_numpy()
    if exog is not None:
        valid &= exog.notna().all(axis=1).to_numpy()
    if not valid.all():
        series = series.iloc[valid]
        if exog is not None:
            exog = exog.iloc[valid]
        index = index[valid]
    training_end = pd.Timestamp(training_range[1])
    training_position = int((pd.DatetimeIndex(index) <= training_end).sum())
    if training_position < 10:
        raise ValueError(
            f"训练期有效样本只有 {training_position} 个，至少需要 10 个"
        )
    return series, exog, pd.DatetimeIndex(index), training_position


def _render_accuracy_report(
    st_obj,
    report: ForecastAccuracyReport,
    *,
    download_key: str,
    download_name: str,
) -> None:
    """以统一表格、误差图和 Excel 下载结果展示评估结果。"""
    st_obj.markdown("**误差指标**")
    st_obj.dataframe(report.error_table, width="stretch")
    _render_error_metric_explanation(st_obj)
    if report.horizon_error_table is not None:
        st_obj.markdown("**误差指标（按预测步长）**")
        st_obj.dataframe(report.horizon_error_table, width="stretch")
        _render_error_metric_explanation(st_obj)
    st_obj.markdown("**方向性指标**")
    direction_columns = [
        column
        for column in (
            "对象",
            "方向命中率",
            "相对基准胜率",
            "趋势相关系数",
            "方向有效样本数",
            "覆盖率",
        )
        if column in report.direction_table.columns
    ]
    st_obj.dataframe(
        report.direction_table.loc[:, direction_columns],
        width="stretch",
    )
    _render_direction_metric_explanation(st_obj)
    if report.horizon_direction_table is not None:
        st_obj.markdown("**方向性指标（按预测步长）**")
        horizon_direction_columns = [
            "步长",
            *direction_columns,
        ]
        st_obj.dataframe(
            report.horizon_direction_table.loc[:, horizon_direction_columns],
            width="stretch",
        )
        _render_direction_metric_explanation(st_obj)
    for note in report.notes:
        st_obj.caption(note)
    detail = report.point_table.drop(columns=["方向参考"], errors="ignore")
    if np.isfinite(detail["误差"].to_numpy(dtype=float)).any():
        render_forecast_error_chart(st_obj, detail)
    st_obj.download_button(
        "下载结果",
        data=build_accuracy_workbook(report),
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=download_key,
        type="primary",
    )


def _render_error_metric_explanation(st_obj) -> None:
    """展示误差指标及样本覆盖字段的计算口径。"""
    with st_obj.expander("指标说明"):
        st_obj.caption("MPE 为带符号百分比误差；MAPE、sMAPE 以百分比点显示。")
        st_obj.markdown(
            """
- **MAE**：平均绝对误差 = mean(|预测值 − 实际值|)，越小越好。
- **RMSE**：均方根误差 = sqrt(mean((预测值 − 实际值)²))；对较大的误差更敏感，越小越好。
- **MPE**：平均百分比误差 = mean((预测值 − 实际值) / 实际值) × 100%；正值表示整体高估，负值表示整体低估。
- **MAPE**：平均绝对百分比误差 = mean(|(预测值 − 实际值) / 实际值|) × 100%，越小越好。
- **sMAPE**：对称平均绝对百分比误差 = mean(2 × |预测值 − 实际值| / (|实际值| + |预测值|)) × 100%；两者同时为 0 时该期计为 0，越小越好。
- **有效样本数**：实际值和预测值均为有限数值、实际参与误差计算的配对数量。
- **百分比指标样本数**：实际值非 0 且实际值和预测值均为有限数值、参与 MPE/MAPE 计算的数量。
- **覆盖率**：有效样本数 ÷ 当前表格对应阶段的总期数。

MPE、MAPE 和 sMAPE 的结果以百分比点记录；实际值为 0 的观测不参与 MPE 和 MAPE，缺失或非有限观测不参与误差指标计算。
"""
        )


def _render_direction_metric_explanation(st_obj) -> None:
    """展示方向性指标及样本覆盖字段的计算口径。"""
    with st_obj.expander("指标说明"):
        st_obj.markdown(
            """
- **方向命中率**：比较实际变化与预测变化的符号，计算为 mean(sign(实际值 − 方向参考) = sign(预测值 − 方向参考))；越高越好。
- **相对基准胜率**：模型绝对误差严格小于朴素基准绝对误差的期数 ÷ 有效比较期数；平局计入分母但不计为胜利，越高越好。
- **趋势相关系数**：实际值路径与预测值路径的 Pearson 相关系数，衡量共同变动方向，不代表绝对误差大小；越接近 1 表示同向变化越强。
- **方向有效样本数**：实际值、预测值和方向参考均为有限数值、实际参与方向判断的数量。
- **覆盖率**：方向有效样本数 ÷ 当前表格对应阶段的总期数。
- **对象**：当前预测窗口显示“拟合表现/样本外表现”；历史滚动回测显示“模型/朴素基准”。

方向参考在拟合期使用前一期实际值，在样本外预测和滚动回测中使用预测起点的最后一个实际值。变化为 0 与变化为 0 视为方向一致。
"""
        )


def _render_future_exog_editor(
    st_obj,
    dataset,
    model_nobs: int,
    model_dates: pd.DatetimeIndex | None,
    total_steps: int,
    exog_names: tuple[str, ...],
    forecast_dates: pd.DatetimeIndex | None = None,
    scope: ModelPageScope = SARIMAX_SCOPE,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """从数据集预填未来外生路径，并允许用户选择来源列及编辑数值。"""
    numeric = [] if dataset is None else numeric_variable_names(dataset.frame)
    if not numeric:
        st_obj.error("当前数据表没有可用的数值列，无法提供未来外生变量路径。")
        empty = build_future_exog(
            None,
            model_nobs,
            model_dates,
            total_steps,
            (),
            exog_names,
            forecast_dates,
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
            key=f"{scope.key_prefix}_future_exog_source_{position}",
            help="从当前数据表选择该模型外生变量的未来路径。",
        )
        source_columns.append(selected)
    source_columns = tuple(source_columns)
    if not source_columns:
        empty = build_future_exog(
            None,
            model_nobs,
            model_dates,
            total_steps,
            (),
            exog_names,
            forecast_dates,
        )
        return empty, source_columns

    editor_frame = build_future_exog(
        dataset,
        model_nobs,
        model_dates,
        total_steps,
        source_columns,
        exog_names,
        forecast_dates,
    )
    editor_signature = stable_signature(
        {
            "start": int(model_nobs),
            "steps": total_steps,
            "sources": source_columns,
            "index": [str(value) for value in editor_frame.index],
        }
    )
    if scope.state.get("future_exog_editor_signature") != editor_signature:
        st_obj.session_state.pop(scope.key("future_exog_editor"), None)
        scope.state.set("future_exog_editor_signature", editor_signature)
    st_obj.markdown("**未来外生变量路径**")
    st_obj.caption("默认从当前数据表提取；空值可直接在下表补录。")
    edited = st_obj.data_editor(
        editor_frame,
        key=scope.key("future_exog_editor"),
        num_rows="fixed",
    )
    return edited.astype(float), source_columns


__all__ = ["render_forecast_section"]
