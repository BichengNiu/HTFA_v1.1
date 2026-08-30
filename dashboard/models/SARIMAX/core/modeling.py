"""动态回归核心编排 facade（无 Streamlit 依赖）。

输入校验、模型族路由、诊断和预测均有独立 module；本模块只保留跨族
编排和稳定的核心导入入口。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from dashboard.models.SARIMAX.core.ardl_config import (
    ARDLConfig,
    AutoARDLConfig,
)
from dashboard.models.SARIMAX.core.ardl_modeling import fit_ardl, fit_auto_ardl
from dashboard.models.SARIMAX.core.diagnostics import (
    recommended_residual_diagnostic_lags,
    run_residual_diagnostics,
)
from dashboard.models.SARIMAX.core.forecasting import (
    build_prediction_table,
    produce_forecast,
)
from dashboard.models.SARIMAX.core.forecast_planning import future_dates
from dashboard.models.SARIMAX.core.rdl_config import AutoRDLConfig, RDLConfig
from dashboard.models.SARIMAX.core.rdl_modeling import fit_auto_rdl, fit_rdl
from dashboard.models.SARIMAX.core.sarimax_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.core.sarimax_modeling import (
    build_auto_sarimax_criterion_table,
    fit_auto_sarimax,
    fit_sarimax,
    format_sarimax_order,
    select_auto_sarimax_candidate,
    select_auto_sarimax_result,
)

MIN_OBSERVATIONS = 10
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
    | AutoRDLConfig
    | ARDLConfig
    | AutoARDLConfig
)


def _is_dynamic_regression(config: DynamicConfig) -> bool:
    return isinstance(
        config,
        (RDLConfig, AutoRDLConfig, ARDLConfig, AutoARDLConfig),
    )


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
        missing = int(exog.isna().sum().sum())
        if missing:
            problems.append(
                f"外生变量存在 {missing} 个缺失值，拟合时将按 missing='drop' "
                "丢弃对应行"
            )

    if _is_dynamic_regression(config):
        if exog is None or exog.shape[1] == 0:
            problems.append("RDL/ARDL 至少需要选择一个解释变量")
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
    elif isinstance(config, (AutoSARIMAXConfig, AutoRDLConfig)):
        seasonal_period = (
            config.s
            if isinstance(config, AutoSARIMAXConfig)
            else config.error.s
        )
    elif config.seasonal:
        seasonal_period = config.period or 0
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
        可选的外生变量表；RDL/ARDL 必须提供。
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
    if exog is None:
        raise ValueError("RDL/ARDL 需要解释变量")
    if isinstance(config, RDLConfig):
        return fit_rdl(series, exog, config)
    if isinstance(config, AutoRDLConfig):
        return fit_auto_rdl(
            series,
            exog,
            config,
            progress_callback=progress_callback,
        )
    if isinstance(config, ARDLConfig):
        return fit_ardl(series, exog, config)
    if isinstance(config, AutoARDLConfig):
        return fit_auto_ardl(
            series,
            exog,
            config,
            progress_callback=progress_callback,
        )
    raise TypeError(f"不支持的动态回归配置：{type(config)!r}")


__all__ = [
    "MIN_OBSERVATIONS",
    "DynamicConfig",
    "build_auto_sarimax_criterion_table",
    "build_prediction_table",
    "fit_ardl",
    "fit_auto_ardl",
    "fit_auto_rdl",
    "fit_auto_sarimax",
    "fit_dynamic_model",
    "fit_rdl",
    "fit_sarimax",
    "format_sarimax_order",
    "future_dates",
    "produce_forecast",
    "recommended_residual_diagnostic_lags",
    "run_residual_diagnostics",
    "select_auto_sarimax_candidate",
    "select_auto_sarimax_result",
    "translate_ts_error",
    "validate_fit_inputs",
]
