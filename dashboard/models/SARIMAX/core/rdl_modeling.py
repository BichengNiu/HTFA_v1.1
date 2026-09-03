"""RDL 传递函数与手动 SARIMAX 误差的拟合实现。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from Ts.TsModels import (
    EventSpec,
    RationalLagSpec,
    SARIMAX,
    SARIMAXResult,
    build_event_matrix,
)

from dashboard.models.SARIMAX.core.rdl_config import (
    RDLConfig,
    RDLInterventionConfig,
    RDL_INTERVENTION_NAME,
)


@dataclass(frozen=True)
class RDLInterventionAnalysis:
    """已拟合 RDL 干预变量的历史路径与事实/反事实对比。"""

    intervention_path: pd.Series
    dynamic_response: pd.Series
    factual_mean: pd.Series
    counterfactual_mean: pd.Series
    effect: pd.Series
    relative_effect: pd.Series
    log_scale: bool

    def table(self) -> pd.DataFrame:
        """返回供表格和图形共同使用的日期对齐结果表。"""
        return pd.DataFrame(
            {
                "I 干预路径": self.intervention_path,
                "RDL 动态响应": self.dynamic_response,
                "有干预 Y": self.factual_mean,
                "无干预 Y": self.counterfactual_mean,
                "干预差异": self.effect,
                "相对变化（%）": self.relative_effect,
            }
        )


def build_rdl_intervention_path(
    model_index: pd.Index,
    intervention: RDLInterventionConfig,
) -> pd.Series:
    """按模型观测索引生成 RDL 干预变量 I 的 0/1 路径。"""
    if not isinstance(intervention, RDLInterventionConfig):
        raise TypeError("intervention 必须是 RDLInterventionConfig")
    try:
        index = pd.DatetimeIndex(pd.to_datetime(model_index))
    except (TypeError, ValueError) as exc:
        raise ValueError("干预分析要求模型索引是有效日期") from exc
    if len(index) == 0 or index.hasnans:
        raise ValueError("干预分析要求模型索引非空且不含无效日期")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("干预分析要求模型日期严格递增且不能重复")
    try:
        if intervention.start_date not in index:
            raise ValueError("干预起始日期必须存在于模型观测日期")
        if (
            intervention.kind == "temporary"
            and intervention.end_date not in index
        ):
            raise ValueError("临时干预结束日期必须存在于模型观测日期")
    except TypeError as exc:
        raise ValueError("干预日期与模型索引的时区必须一致") from exc

    event = EventSpec(
        name="intervention",
        dates=[intervention.start_date],
        kind=intervention.kind,
        end_date=intervention.end_date,
        date_rule="exact",
    )
    matrix, _ = build_event_matrix(index, [event], calendar=index)
    return matrix.iloc[:, 0].rename(RDL_INTERVENTION_NAME)


def validate_rdl_intervention(
    series_index: pd.Index,
    config: RDLConfig,
) -> list[str]:
    """返回 RDL 干预路径的可识别性问题。"""
    if config.intervention is None:
        return []
    try:
        path = build_rdl_intervention_path(series_index, config.intervention)
    except (TypeError, ValueError) as exc:
        return [f"干预路径无效：{exc}"]

    values = path.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return ["干预路径包含非有限值"]
    if len(np.unique(values)) < 2:
        return ["干预路径恒定，无法与误差模型的常数/趋势项区分"]

    trend = config.error.trend
    baseline = []
    if "c" in trend:
        baseline.append(np.ones(len(values)))
    if "t" in trend:
        baseline.append(np.arange(len(values), dtype=float))
    if baseline:
        baseline_matrix = np.column_stack(baseline)
        combined = np.column_stack([baseline_matrix, values])
        if np.linalg.matrix_rank(combined) == np.linalg.matrix_rank(
            baseline_matrix
        ):
            return ["干预路径与误差模型的常数/趋势项完全共线"]
    return []


def _rdl_specs(config: RDLConfig) -> dict[str, RationalLagSpec]:
    """将 UI 层传递函数配置转换为 Ts 的不可变规格。"""
    specs = {}
    for item in config.inputs:
        numerator, denominator, delay, initialization = item.specification()
        specs[item.name] = RationalLagSpec(
            numerator=numerator,
            denominator=denominator,
            delay=delay,
            initialization=initialization,
        )
    return specs


def build_rdl_model(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: RDLConfig,
) -> SARIMAX:
    """构造尚未拟合的固定传递函数加 SARIMAX 误差 RDL 模型。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        普通外生变量表；启用干预分析且无普通 X 时可以为 ``None``。
    config : RDLConfig
        固定传递函数配置和误差模型配置。

    Returns
    -------
    SARIMAX
        尚未拟合的 Ts 模型对象。
    """
    if config.intervention is not None:
        intervention_problems = validate_rdl_intervention(series.index, config)
        if intervention_problems:
            raise ValueError("；".join(intervention_problems))
        intervention_path = build_rdl_intervention_path(
            series.index,
            config.intervention,
        ).to_frame()
        if exog is None:
            exog = intervention_path
        else:
            if not exog.index.equals(series.index):
                raise ValueError("外生变量与目标序列索引不一致")
            if RDL_INTERVENTION_NAME in exog.columns:
                raise ValueError(
                    f"普通外生变量不能使用保留名称 {RDL_INTERVENTION_NAME!r}"
                )
            exog = pd.concat([exog.copy(), intervention_path], axis=1)
    elif exog is None:
        raise ValueError("RDL 没有普通外生变量或干预变量 I")

    error = config.error
    model = SARIMAX(
        series,
        order=error.order,
        seasonal_order=error.seasonal_order,
        trend=error.trend,
        exog=exog,
        log=error.log,
        enforce_stationarity=error.enforce_stationarity,
        enforce_invertibility=error.enforce_invertibility,
        distributed_lags=_rdl_specs(config),
        enforce_distributed_lag_stability=config.enforce_distributed_lag_stability,
    )
    return model


def fit_rdl(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: RDLConfig,
) -> SARIMAXResult:
    """拟合固定传递函数加 SARIMAX 误差的 RDL 模型。"""
    model = build_rdl_model(series, exog, config)
    error = config.error
    return model.fit(
        method=error.fit_method,
        maxiter=error.maxiter,
        cov_type=error.cov_type,
    )


def build_rdl_intervention_analysis(
    result: SARIMAXResult,
    intervention: RDLInterventionConfig,
) -> RDLInterventionAnalysis:
    """基于公开 RDL 结果构造干预路径和事实/反事实对比。"""
    if not isinstance(intervention, RDLInterventionConfig):
        raise TypeError("intervention 必须是 RDLInterventionConfig")
    dates = getattr(result, "dates", None)
    if dates is None:
        raise ValueError("干预分析结果必须包含模型日期")
    path = build_rdl_intervention_path(dates, intervention)
    distributed = getattr(result, "distributed_lags", {})
    input_result = distributed.get(RDL_INTERVENTION_NAME)
    if input_result is None:
        raise ValueError("拟合结果缺少干预变量 I 的 RDL 结果")
    dynamic = pd.Series(
        input_result.filter(path.to_numpy(dtype=float)),
        index=path.index,
        name="RDL 动态响应",
        dtype=float,
    )
    fitted_values = getattr(result, "fitted_values", None)
    if fitted_values is None or len(fitted_values) != len(path):
        raise ValueError("拟合结果的拟合值与干预路径长度不一致")
    factual = pd.Series(
        np.asarray(fitted_values, dtype=float),
        index=path.index,
        name="有干预 Y",
    )
    valid = np.isfinite(factual.to_numpy())
    dynamic_values = dynamic.to_numpy(dtype=float, copy=True)
    dynamic_values[~valid] = np.nan
    dynamic = pd.Series(dynamic_values, index=path.index, name=dynamic.name)

    if bool(getattr(result, "log", False)):
        factor = np.exp(dynamic.to_numpy(dtype=float))
        counterfactual_values = factual.to_numpy(dtype=float) / factor
        relative_values = 100.0 * (factor - 1.0)
    else:
        counterfactual_values = factual.to_numpy(dtype=float) - dynamic_values
        relative_values = np.full(len(path), np.nan)
    counterfactual_values[~valid] = np.nan
    effect_values = factual.to_numpy(dtype=float) - counterfactual_values
    effect_values[~valid] = np.nan
    relative_values[~valid] = np.nan
    return RDLInterventionAnalysis(
        intervention_path=path,
        dynamic_response=dynamic,
        factual_mean=factual,
        counterfactual_mean=pd.Series(
            counterfactual_values,
            index=path.index,
            name="无干预 Y",
        ),
        effect=pd.Series(effect_values, index=path.index, name="干预差异"),
        relative_effect=pd.Series(
            relative_values,
            index=path.index,
            name="相对变化（%）",
        ),
        log_scale=bool(getattr(result, "log", False)),
    )


__all__ = [
    "RDLInterventionAnalysis",
    "build_rdl_intervention_analysis",
    "build_rdl_intervention_path",
    "build_rdl_model",
    "fit_rdl",
    "validate_rdl_intervention",
]
