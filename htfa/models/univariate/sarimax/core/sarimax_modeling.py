"""SARIMAX 手动拟合与自动选阶实现。"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from Ts.TsModels import AutoModelResult, AutoSARIMAX, SARIMAX, SARIMAXResult

from htfa.models.univariate.sarimax.core.config_shared import AUTO_CRITERIA
from htfa.models.univariate.sarimax.core.sarimax_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)

ProgressCallback = Callable[[int, int], None]


def build_sarimax_model(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: SARIMAXConfig,
) -> SARIMAX:
    """按配置构造尚未拟合的 SARIMAX 模型。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表。
    config : SARIMAXConfig
        手动 SARIMAX 配置。

    Returns
    -------
    SARIMAX
        尚未拟合的 Ts 模型对象。
    """
    return SARIMAX(
        series,
        order=config.order,
        seasonal_order=config.seasonal_order,
        trend=config.trend,
        exog=exog,
        exog_operators=config.operator_mapping(),
        log=config.log,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )


def fit_sarimax(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: SARIMAXConfig,
) -> SARIMAXResult:
    """按手动配置拟合 SARIMAX 模型并返回 Ts 结果对象。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表。
    config : SARIMAXConfig
        手动 SARIMAX 配置。

    Returns
    -------
    SARIMAXResult
        已拟合的 SARIMAX 结果对象。
    """
    model = build_sarimax_model(series, exog, config)
    return model.fit(
        method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
    )


def fit_auto_sarimax(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: AutoSARIMAXConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AutoModelResult:
    """按搜索范围自动选阶并返回 Ts 结果对象。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表。
    config : AutoSARIMAXConfig
        自动 SARIMAX 配置。
    progress_callback : callable, optional
        每完成一个候选模型后，在主进程中调用
        ``callback(completed, total)``。

    Returns
    -------
    AutoModelResult
        自动 SARIMAX 候选搜索结果。
    """
    model = AutoSARIMAX(
        series,
        p=config.p,
        d=config.d,
        q=config.q,
        P=config.P,
        D=config.D,
        Q=config.Q,
        s=config.s,
        trend=config.trend,
        criterion=config.criterion,
        exog=exog,
        exog_operators=config.operator_mapping(),
        log=config.log,
        fit_method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )
    return model.fit(progress_callback=progress_callback)


def format_sarimax_order(
    order: tuple[int, int, int],
    seasonal_order: tuple[int, int, int, int] | None = None,
) -> str:
    """将 SARIMAX 阶数格式化为完整的 `(p,d,q)(P,D,Q,S)` 标签。

    Parameters
    ----------
    order : tuple[int, int, int]
        非季节阶数 `(p,d,q)`。
    seasonal_order : tuple[int, int, int, int] or None, optional
        季节阶数 `(P,D,Q,S)`；省略时使用无季节项 `(0,0,0,0)`。

    Returns
    -------
    str
        形如 ``SARIMAX(2, 0, 1)(1, 0, 1, 252)`` 的完整模型标签。
    """
    seasonal = (0, 0, 0, 0) if seasonal_order is None else tuple(seasonal_order)
    return f"SARIMAX{tuple(order)}{seasonal}"


def build_auto_sarimax_criterion_table(result: AutoModelResult) -> pd.DataFrame:
    """构建自动 SARIMAX 候选模型的多准则比较表。

    Parameters
    ----------
    result : AutoModelResult
        AutoSARIMAX 搜索结果，必须包含候选模型结果。

    Returns
    -------
    pandas.DataFrame
        行为候选模型，列为模型标签、AIC、BIC、HQIC 和 AICC。
        信息准则数值越小越优。
    """
    criterion_values = result.criterion_table
    rows = []
    for index, order in enumerate(result.candidate_orders):
        seasonal = (
            result.candidate_seasonal_orders[index]
            if index < len(result.candidate_seasonal_orders)
            else None
        )
        label = format_sarimax_order(order, seasonal)
        rows.append(
            {
                "模型": label,
                **{
                    criterion.upper(): round(
                        float(criterion_values.iloc[index][criterion]), 6
                    )
                    for criterion in AUTO_CRITERIA
                },
            }
        )
    return pd.DataFrame(rows, columns=["模型", *(c.upper() for c in AUTO_CRITERIA)])


def select_auto_sarimax_result(
    result: AutoModelResult,
    criterion: str,
) -> AutoModelResult:
    """按指定信息准则从已有候选结果中选择最终模型。

    并行搜索返回轻量候选摘要时，仅对新选中的阶数重新拟合一次完整
    SARIMAX；串行搜索仍直接复用已有候选结果。

    Parameters
    ----------
    result : AutoModelResult
        已完成网格搜索的 AutoSARIMAX 结果。
    criterion : str
        选择准则，必须是 ``AUTO_CRITERIA`` 中的一项。

    Returns
    -------
    AutoModelResult
        以指定准则最小候选模型为 ``best_result`` 的结果对象。
    """
    if criterion not in AUTO_CRITERIA:
        raise ValueError(f"criterion 必须是 {AUTO_CRITERIA} 之一")
    values = pd.to_numeric(
        result.criterion_table[criterion], errors="coerce"
    ).to_numpy(dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError(f"{criterion} 没有可用的候选值")
    best_index = int(np.where(finite, values, np.inf).argmin())
    return _select_auto_sarimax_candidate(
        result,
        best_index,
        criterion=criterion,
        criterion_values=values.tolist(),
    )


def select_auto_sarimax_candidate(
    result: AutoModelResult,
    candidate_index: int,
) -> AutoModelResult:
    """从候选表按行号选择并重新拟合任意 SARIMAX 候选模型。

    Parameters
    ----------
    result : AutoModelResult
        已完成网格搜索的 AutoSARIMAX 结果。
    candidate_index : int
        候选表中的零基行号。

    Returns
    -------
    AutoModelResult
        以指定候选模型为 ``best_result`` 的结果对象。

    Raises
    ------
    TypeError
        ``candidate_index`` 不是整数时。
    ValueError
        候选行号超出候选表范围时。
    """
    if isinstance(candidate_index, bool) or not isinstance(
        candidate_index, (int, np.integer)
    ):
        raise TypeError("candidate_index 必须是整数")
    candidate_index = int(candidate_index)
    if not 0 <= candidate_index < len(result.candidate_orders):
        raise ValueError("candidate_index 超出候选表范围")
    criterion = getattr(result, "selection_criterion", AUTO_CRITERIA[0])
    values = pd.to_numeric(
        result.criterion_table[criterion], errors="coerce"
    ).to_numpy(dtype=float)
    return _select_auto_sarimax_candidate(
        result,
        candidate_index,
        criterion=criterion,
        criterion_values=values.tolist(),
    )


def _select_auto_sarimax_candidate(
    result: AutoModelResult,
    candidate_index: int,
    *,
    criterion: str,
    criterion_values: list[float],
) -> AutoModelResult:
    """按候选行号构建重新拟合后的 AutoSARIMAX 结果。"""
    seasonal = (
        result.candidate_seasonal_orders[candidate_index]
        if candidate_index < len(result.candidate_seasonal_orders)
        else None
    )
    best_result = result._refit_candidate(candidate_index)
    return AutoModelResult.from_search(
        best_result=best_result,
        best_order=result.candidate_orders[candidate_index],
        candidate_results=result.candidate_results,
        candidate_orders=result.candidate_orders,
        criterion_values=criterion_values,
        selection_criterion=criterion,
        search_method=result.search_method,
        n_attempted=result.n_attempted,
        best_seasonal_order=seasonal,
        candidate_seasonal_orders=result.candidate_seasonal_orders,
        search_messages=result.search_messages,
        search_metadata=getattr(result, "search_metadata", None),
        candidate_model_kwargs=result._candidate_model_kwargs,
        candidate_fit_kwargs=result._candidate_fit_kwargs,
    )


__all__ = [
    "build_auto_sarimax_criterion_table",
    "build_sarimax_model",
    "fit_auto_sarimax",
    "fit_sarimax",
    "format_sarimax_order",
    "select_auto_sarimax_candidate",
    "select_auto_sarimax_result",
]
