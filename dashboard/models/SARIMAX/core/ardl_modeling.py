"""标准 ARDL 拟合实现。"""

from __future__ import annotations

import pandas as pd
from Ts.TsModels import ARDL

from dashboard.models.SARIMAX.core.ardl_config import ARDLConfig


def fit_ardl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: ARDLConfig,
):
    """拟合标准 ARDL，而非把 SARIMAX AR 误称为 ARDL。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame
        外生变量表。
    config : ARDLConfig
        标准 ARDL 配置。

    Returns
    -------
    object
        Ts 标准 ARDL 拟合结果。
    """
    error = config.error
    model_kwargs = {}
    fit_kwargs = {"cov_type": config.cov_type}
    if error is not None:
        model_kwargs.update(
            error_order=error.order,
            error_seasonal_order=error.seasonal_order,
            error_enforce_stationarity=error.enforce_stationarity,
            error_enforce_invertibility=error.enforce_invertibility,
        )
        fit_kwargs.update(
            error_method=error.fit_method,
            error_maxiter=error.maxiter,
            error_cov_type=error.cov_type,
        )
    model = ARDL(
        series,
        lags=config.lags,
        exog=exog,
        order=config.order_mapping(),
        trend=config.trend,
        causal=config.causal,
        seasonal=config.seasonal,
        period=config.period,
        hold_back=config.hold_back,
        log=config.log,
        **model_kwargs,
    )
    return model.fit(**fit_kwargs)


__all__ = ["fit_ardl"]
