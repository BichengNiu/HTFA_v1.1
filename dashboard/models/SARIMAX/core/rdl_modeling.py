"""RDL 传递函数与手动 SARIMAX 误差的拟合实现。"""

from __future__ import annotations

import pandas as pd
from Ts.TsModels import RationalLagSpec, SARIMAX, SARIMAXResult

from dashboard.models.SARIMAX.core.rdl_config import RDLConfig


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


def fit_rdl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: RDLConfig,
) -> SARIMAXResult:
    """拟合固定传递函数加 SARIMAX 误差的 RDL 模型。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame
        外生变量表。
    config : RDLConfig
        固定传递函数配置和误差模型配置。

    Returns
    -------
    SARIMAXResult
        已拟合的 RDL 结果对象。
    """
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
    return model.fit(
        method=error.fit_method,
        maxiter=error.maxiter,
        cov_type=error.cov_type,
    )


__all__ = ["fit_rdl"]
