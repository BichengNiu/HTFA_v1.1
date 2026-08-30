"""标准 ARDL 与自动 ARDL 拟合实现。"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from Ts.TsModels import ARDL, AutoARDL, AutoARDLResult

from dashboard.models.SARIMAX.core.ardl_config import ARDLConfig, AutoARDLConfig

ProgressCallback = Callable[[int, int], None]


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
    )
    return model.fit(cov_type=config.cov_type)


def fit_auto_ardl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: AutoARDLConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AutoARDLResult:
    """按 AIC/BIC 自动选择标准 ARDL 的目标和逐输入滞后。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame
        外生变量表。
    config : AutoARDLConfig
        自动 ARDL 配置。
    progress_callback : callable, optional
        每完成一个候选模型后，在主进程中调用
        ``callback(completed, total)``。

    Returns
    -------
    AutoARDLResult
        自动 ARDL 候选搜索结果。
    """
    model = AutoARDL(
        series,
        maxlag=config.maxlag,
        exog=exog,
        maxorder=config.maxorder_mapping(),
        trend=config.trend,
        criterion=config.criterion,
        search_method=config.search_method,
        causal=config.causal,
        seasonal=config.seasonal,
        period=config.period,
        hold_back=config.hold_back,
        log=config.log,
    )
    return model.fit(
        cov_type=config.cov_type,
        progress_callback=progress_callback,
    )


__all__ = ["fit_ardl", "fit_auto_ardl"]
