"""动态回归核心编排 facade（无 Streamlit 依赖）。

输入校验、模型族路由、诊断和预测均有独立 module；本模块只保留跨族
编排和稳定的核心导入入口。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
from Ts.TsMetrics import RollingOrigin, evaluate_forecasts

from dashboard.models.SARIMAX.core.ardl_config import ARDLConfig
from dashboard.models.SARIMAX.core.ardl_modeling import (
    build_ardl_model,
    fit_ardl,
)
from dashboard.models.SARIMAX.core.diagnostics import (
    recommended_residual_diagnostic_lags,
    run_residual_diagnostics,
)
from dashboard.models.SARIMAX.core.forecasting import (
    build_prediction_table,
    produce_forecast,
)
from dashboard.models.SARIMAX.core.forecast_planning import future_dates
from dashboard.models.SARIMAX.core.rdl_config import RDLConfig
from dashboard.models.SARIMAX.core.rdl_modeling import (
    build_rdl_intervention_analysis,
    build_rdl_model,
    fit_rdl,
    validate_rdl_intervention,
)
from dashboard.models.SARIMAX.core.sarimax_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.core.sarimax_modeling import (
    build_auto_sarimax_criterion_table,
    build_sarimax_model,
    fit_auto_sarimax,
    fit_sarimax,
    format_sarimax_order,
    select_auto_sarimax_candidate,
    select_auto_sarimax_result,
)

MIN_OBSERVATIONS = 10
# Rolling refits are expensive; retain only the most recent complete origins.
MAX_ROLLING_ORIGINS = 100
ProgressCallback = Callable[[int, int], None]


# Ts 包英文错误消息 → 用户可读中文提示的映射（按出现顺序匹配）。
_SARIMAX_ERROR_HINTS = (
    (
        "Need at least 10 observations",
        "样本量不足：SARIMAX 至少需要 10 个观测值",
    ),
    (
        "log transformation requires strictly positive data",
        "已启用 log 变换，但数据存在非正值",
    ),
    (
        "log transformation requires strictly positive exogenous data",
        "已启用外生变量 log 变换，但数据存在非正值",
    ),
    (
        "SARIMAX optimization failed to converge",
        "模型优化未收敛，请尝试更换优化器、增大最大迭代次数或简化阶数",
    ),
    (
        "future exog",
        "未来外生变量数据有误",
    ),
    (
        "exog",
        "外生变量数据有误",
    ),
    (
        "seasonal_order",
        "季节阶数设置有误",
    ),
    (
        "rank deficient",
        "外生变量设计与趋势项存在共线性或全零列",
    ),
)


def translate_ts_error(error: Exception) -> str:
    """把 Ts 包抛出的异常转译为面向用户的中文消息。

    Parameters
    ----------
    error : Exception
        Ts 或模型编排过程中捕获的异常。

    Returns
    -------
    str
        可直接展示给用户的中文错误信息。
    """
    message = str(error).strip()
    for fragment, hint in _SARIMAX_ERROR_HINTS:
        if fragment in message:
            return f"{hint}：{message}"
    if message:
        return message
    return (
        f"{type(error).__name__}：异常未提供详细信息；"
        "请缩小自动选阶范围后重试，并检查运行日志。"
    )


DynamicConfig = (
    SARIMAXConfig
    | AutoSARIMAXConfig
    | RDLConfig
    | ARDLConfig
)


def _is_dynamic_regression(config: DynamicConfig) -> bool:
    return isinstance(
        config,
        (RDLConfig, ARDLConfig),
    )


def fit_input_warnings(exog: pd.DataFrame | None) -> list[str]:
    """返回不会阻止 SARIMAX 拟合的输入提示。"""
    if exog is None:
        return []
    missing = int(exog.isna().sum().sum())
    if not missing:
        return []
    return [
        f"外生变量存在 {missing} 个缺失值，拟合时将按 missing='drop' "
        "丢弃对应行"
    ]


def validate_fit_inputs(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
) -> list[str]:
    """拟合前预检，返回用户可读的问题列表；空列表表示可以拟合。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表。
    config : DynamicConfig
        SARIMAX、RDL 或 ARDL 配置对象。

    Returns
    -------
    list[str]
        用户可读的预检问题；没有问题时为空列表。
    """
    problems: list[str] = []
    if series is None:
        problems.append("尚未选择目标变量")
        return problems

    valid = series.dropna()
    if len(valid) < MIN_OBSERVATIONS:
        problems.append(
            f"样本量不足：有效观测 {len(valid)} 个，模型至少需要 "
            f"{MIN_OBSERVATIONS} 个"
        )
    if config.log and len(valid) > 0 and float(valid.min()) <= 0.0:
        problems.append("已启用 log 变换，但目标序列存在非正值")

    if exog is not None:
        if not exog.index.equals(series.index):
            problems.append("外生变量与目标序列索引不一致，请重新选择外生变量")

    if _is_dynamic_regression(config):
        if isinstance(config, RDLConfig):
            if exog is None or exog.shape[1] == 0:
                if config.intervention is None:
                    problems.append("RDL 至少需要一个普通外生变量或干预变量 I")
            problems.extend(validate_rdl_intervention(series.index, config))
        elif exog is None or exog.shape[1] == 0:
            problems.append("ARDL 至少需要选择一个解释变量")
        if series.isna().any() or (
            exog is not None and exog.isna().any().any()
        ):
            problems.append(
                "动态回归不接受缺失导致的非连续样本；请先补齐或删除不完整期"
            )

    seasonal_period = 0
    if isinstance(config, (SARIMAXConfig, RDLConfig)):
        seasonal_period = (
            config.seasonal_order[3]
            if isinstance(config, SARIMAXConfig)
            else config.error.seasonal_order[3]
        )
    elif isinstance(config, AutoSARIMAXConfig):
        seasonal_period = config.s
    elif isinstance(config, ARDLConfig):
        seasonal_period = config.period or 0
        error_period = (
            0 if config.error is None else config.error.seasonal_order[3]
        )
        seasonal_period = max(seasonal_period, error_period)
    if seasonal_period > 0 and len(valid) < 2 * seasonal_period:
        problems.append(
            f"季节周期 s={seasonal_period} 过大：至少需要 {2 * seasonal_period} "
            "个观测才能估计季节项"
        )
    return problems


def fit_dynamic_model(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
    *,
    progress_callback: ProgressCallback | None = None,
):
    """按模型族和配置方式分发到各族 module 的唯一拟合入口。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表；RDL 在启用干预变量 I 时可以没有普通 X，
        ARDL 必须提供普通解释变量。
    config : DynamicConfig
        SARIMAX、RDL 或 ARDL 配置对象。
    progress_callback : callable, optional
        自动选阶时，每完成一个候选模型后在主进程中调用
        ``callback(completed, total)``；手动模式忽略该回调。

    Returns
    -------
    object
        对应模型族的 Ts 拟合结果。
    """
    if isinstance(config, SARIMAXConfig):
        return fit_sarimax(series, exog, config)
    if isinstance(config, AutoSARIMAXConfig):
        return fit_auto_sarimax(
            series,
            exog,
            config,
            progress_callback=progress_callback,
        )
    if isinstance(config, RDLConfig):
        return fit_rdl(series, exog, config)
    if isinstance(config, ARDLConfig):
        if exog is None:
            raise ValueError("ARDL 需要解释变量")
        return fit_ardl(series, exog, config)
    raise TypeError(f"不支持的动态回归配置：{type(config)!r}")


def evaluation_config(config: DynamicConfig, result: object | None = None):
    """返回历史评估要固定使用的模型结构。

    自动 SARIMAX 只在训练阶段选阶；历史滚动回测固定当前选中的最优阶数，
    不在每个滚动窗口重新搜索候选网格。

    Parameters
    ----------
    config : DynamicConfig
        当前页面使用的模型配置。
    result : object, optional
        当前已拟合结果；自动 SARIMAX 需要从其中读取选中的最优模型。

    Returns
    -------
    DynamicConfig
        手动配置原样返回；自动 SARIMAX 返回固定最优阶数的 SARIMAXConfig。
    """
    if not isinstance(config, AutoSARIMAXConfig):
        return config
    best = getattr(result, "best_result", None)
    if best is None:
        raise ValueError("自动 SARIMAX 尚未产生可用于回测的最优模型")
    return SARIMAXConfig(
        order=best.order,
        seasonal_order=best.seasonal_order,
        exog_operators=best.exog_operators,
        trend=best.trend,
        log=best.log,
        enforce_stationarity=best.stationarity_enforced,
        enforce_invertibility=best.invertibility_enforced,
        fit_method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
    )


def build_evaluation_model(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
    result: object | None = None,
):
    """构造供 Ts 历史滚动回测使用的未拟合模型。

    Parameters
    ----------
    series : pandas.Series
        参与历史回测的完整目标序列。
    exog : pandas.DataFrame or None
        与目标序列对齐的完整外生变量路径。
    config : DynamicConfig
        当前页面模型配置。
    result : object, optional
        当前已拟合结果；自动 SARIMAX 用于固定当前最优阶数。

    Returns
    -------
    object
        满足 Ts 历史评估协议的未拟合模型对象。
    """
    selected = evaluation_config(config, result)
    if isinstance(selected, SARIMAXConfig):
        return build_sarimax_model(series, exog, selected)
    if isinstance(selected, RDLConfig):
        return build_rdl_model(series, exog, selected)
    if isinstance(selected, ARDLConfig):
        if exog is None:
            raise ValueError("ARDL 需要解释变量")
        return build_ardl_model(series, exog, selected)
    raise TypeError(f"不支持的历史评估配置：{type(selected)!r}")


def evaluation_fit_kwargs(config: DynamicConfig, result: object | None = None) -> dict:
    """返回历史滚动回测每个窗口拟合时使用的参数。

    Parameters
    ----------
    config : DynamicConfig
        当前页面模型配置。
    result : object, optional
        当前已拟合结果；自动 SARIMAX 用于固定当前最优阶数。

    Returns
    -------
    dict
        传给 Ts ``evaluate_forecasts`` 的 ``fit_kwargs``。
    """
    selected = evaluation_config(config, result)
    if isinstance(selected, SARIMAXConfig):
        return {
            "method": selected.fit_method,
            "maxiter": selected.maxiter,
            "cov_type": selected.cov_type,
        }
    if isinstance(selected, RDLConfig):
        return {
            "method": selected.error.fit_method,
            "maxiter": selected.error.maxiter,
            "cov_type": selected.error.cov_type,
        }
    if isinstance(selected, ARDLConfig):
        values = {"cov_type": selected.cov_type}
        if selected.error is not None:
            values.update(
                error_method=selected.error.fit_method,
                error_maxiter=selected.error.maxiter,
                error_cov_type=selected.error.cov_type,
            )
        return values
    raise TypeError(f"不支持的历史评估配置：{type(selected)!r}")


def evaluation_seasonal_period(
    config: DynamicConfig,
    result: object | None = None,
) -> int:
    """返回朴素基准采用的季节滞后；无季节项时返回 1。

    Parameters
    ----------
    config : DynamicConfig
        当前页面模型配置。
    result : object, optional
        当前已拟合结果；自动 SARIMAX 用于读取实际选中的季节阶数。

    Returns
    -------
    int
        朴素基准使用的正整数滞后期数。
    """
    selected = evaluation_config(config, result)
    if isinstance(selected, (SARIMAXConfig, RDLConfig)):
        order = (
            selected.seasonal_order
            if isinstance(selected, SARIMAXConfig)
            else selected.error.seasonal_order
        )
        return max(1, int(order[3]))
    if isinstance(selected, ARDLConfig):
        error_period = (
            0
            if selected.error is None
            else selected.error.seasonal_order[3]
        )
        return max(1, int(selected.period or 0), int(error_period))
    return 1


def run_historical_rolling_evaluation(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
    result: object,
    *,
    initial_window: int,
    horizon: int,
):
    """执行固定模型结构的历史滚动回测。

    Parameters
    ----------
    series : pandas.Series
        参与历史回测的完整目标序列。
    exog : pandas.DataFrame or None
        与目标序列对齐的完整外生变量路径。
    config : DynamicConfig
        当前页面模型配置。
    result : object
        当前已拟合结果。
    initial_window : int
        第一个滚动起点可用的训练观测数。
    horizon : int
        每个滚动起点评估的预测期数。

    Returns
    -------
    ForecastComparisonResult
        Ts 返回的历史滚动评估结果。
    """
    estimator = build_evaluation_model(series, exog, config, result)
    scheme = RollingOrigin(
        initial_window=initial_window,
        horizon=horizon,
        step=1,
        max_origins=MAX_ROLLING_ORIGINS,
        window="expanding",
    )
    return evaluate_forecasts(
        {getattr(result, "model_type", "模型"): estimator},
        scheme=scheme,
        fit_kwargs=evaluation_fit_kwargs(config, result),
        on_error="record",
        future_exog=(
            "observed" if getattr(estimator, "exog", None) is not None else None
        ),
    )


def run_training_rolling_evaluation(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
    result: object,
    *,
    horizon: int,
):
    """执行训练集内部的 H 期扩展窗口伪样本外评估。

    Parameters
    ----------
    series : pandas.Series
        仅包含训练期的完整、已对齐目标序列。
    exog : pandas.DataFrame or None
        与训练期目标序列对齐的外生变量表。
    config : DynamicConfig
        当前页面模型配置。
    result : object
        当前已拟合结果；自动 SARIMAX 用于固定当前最优阶数。
    horizon : int
        每个训练期滚动起点评估的预测期数。

    Returns
    -------
    ForecastComparisonResult
        Ts 返回的训练期滚动评估结果。
    """
    if isinstance(horizon, bool) or not isinstance(horizon, int):
        raise TypeError("horizon 必须是正整数")
    if horizon < 1:
        raise ValueError("horizon 必须是正整数")
    initial_window = max(MIN_OBSERVATIONS, 2 * int(horizon))
    return run_historical_rolling_evaluation(
        series,
        exog,
        config,
        result,
        initial_window=initial_window,
        horizon=int(horizon),
    )


def run_fixed_holdout_evaluation(
    result: object,
    *,
    start: int | str | pd.Timestamp,
    end: int | str | pd.Timestamp,
    future_exog: pd.DataFrame | None = None,
    future_dates: pd.DatetimeIndex | None = None,
):
    """复用一次已拟合结果，生成固定起点样本外预测。

    Parameters
    ----------
    result : object
        当前已拟合结果；自动 SARIMAX 会使用其中的最佳拟合结果。
    start : int or datetime-like
        固定起点预测位置或日期。
    end : int or datetime-like
        固定终点预测位置或日期，包含该位置。
    future_exog : pandas.DataFrame or None, optional
        从拟合样本末期到预测终点的已观测外生变量路径。
    future_dates : pandas.DatetimeIndex or None, optional
        预测日期路径；无法从拟合日期推断频率时使用。

    Returns
    -------
    dict[str, Any]
        ``produce_forecast`` 返回的固定起点预测结构。
    """
    selected = getattr(result, "best_result", result)
    return produce_forecast(
        selected,
        start=start,
        end=end,
        dynamic=False,
        future_exog=future_exog,
        future_dates=future_dates,
    )


__all__ = [
    "MIN_OBSERVATIONS",
    "MAX_ROLLING_ORIGINS",
    "DynamicConfig",
    "build_auto_sarimax_criterion_table",
    "build_prediction_table",
    "build_evaluation_model",
    "build_rdl_intervention_analysis",
    "fit_ardl",
    "fit_auto_sarimax",
    "fit_dynamic_model",
    "fit_rdl",
    "fit_sarimax",
    "format_sarimax_order",
    "fit_input_warnings",
    "evaluation_config",
    "evaluation_fit_kwargs",
    "evaluation_seasonal_period",
    "run_historical_rolling_evaluation",
    "run_training_rolling_evaluation",
    "run_fixed_holdout_evaluation",
    "future_dates",
    "produce_forecast",
    "recommended_residual_diagnostic_lags",
    "run_residual_diagnostics",
    "select_auto_sarimax_candidate",
    "select_auto_sarimax_result",
    "translate_ts_error",
    "validate_rdl_intervention",
    "validate_fit_inputs",
]
