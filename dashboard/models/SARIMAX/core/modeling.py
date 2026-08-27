"""SARIMAX 拟合、诊断与预测编排（唯一调用 Ts 包的模块，无 streamlit 依赖）。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from Ts.TsModels import (
    ARDL,
    SARIMAX,
    AutoARDL,
    AutoARDLResult,
    AutoModelResult,
    AutoSARIMAX,
    RationalLagSpec,
    SARIMAXResult,
)

from dashboard.models.SARIMAX.core.model_config import (
    ARDLConfig,
    AutoARDLConfig,
    AutoRDLConfig,
    AutoSARIMAXConfig,
    AUTO_CRITERIA,
    RDLConfig,
    SARIMAXConfig,
)

MIN_OBSERVATIONS = 10

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

_DIAGNOSTIC_ROWS = (
    ("white_noise", "残差自相关（Ljung-Box）"),
    ("normality", "残差正态性（Jarque-Bera）"),
    ("ljung_box", "ARCH 效应（平方残差 Ljung-Box）"),
    ("engle_lm", "ARCH 效应（Engle LM）"),
)


def translate_ts_error(error: Exception) -> str:
    """把 Ts 包抛出的异常转译为面向用户的中文消息。"""
    message = str(error)
    for fragment, hint in _SARIMAX_ERROR_HINTS:
        if fragment in message:
            return f"{hint}：{message}"
    return message


DynamicConfig = (
    SARIMAXConfig
    | AutoSARIMAXConfig
    | RDLConfig
    | AutoRDLConfig
    | ARDLConfig
    | AutoARDLConfig
)


def _is_dynamic_regression(config: DynamicConfig) -> bool:
    return isinstance(config, (RDLConfig, AutoRDLConfig, ARDLConfig, AutoARDLConfig))


def validate_fit_inputs(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
) -> list[str]:
    """拟合前预检，返回用户可读的问题列表；空列表表示可以拟合。"""
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
        if series.isna().any() or (exog is not None and exog.isna().any().any()):
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
        seasonal_period = config.s if isinstance(config, AutoSARIMAXConfig) else config.error.s
    elif config.seasonal:
        seasonal_period = config.period or 0
    if seasonal_period > 0 and len(valid) < 2 * seasonal_period:
        problems.append(
            f"季节周期 s={seasonal_period} 过大：至少需要 {2 * seasonal_period} "
            "个观测才能估计季节项"
        )
    return problems


def fit_sarimax(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: SARIMAXConfig,
) -> SARIMAXResult:
    """按手动配置拟合 SARIMAX 模型并返回 Ts 结果对象。"""
    model = SARIMAX(
        series,
        order=config.order,
        seasonal_order=config.seasonal_order,
        trend=config.trend,
        exog=exog,
        log=config.log,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )
    return model.fit(
        method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
    )


def fit_auto_sarimax(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: AutoSARIMAXConfig,
) -> AutoModelResult:
    """按搜索范围自动选阶并返回 Ts 结果对象。"""
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
        log=config.log,
        fit_method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )
    return model.fit()


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
        label = f"{result.model_type}{order}"
        if seasonal:
            label += f" × {seasonal}"
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
    """按指定信息准则从已有候选结果中选择最终模型，不重新拟合。

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
    seasonal = (
        result.candidate_seasonal_orders[best_index]
        if best_index < len(result.candidate_seasonal_orders)
        else None
    )
    return AutoModelResult.from_search(
        best_result=result.candidate_results[best_index],
        best_order=result.candidate_orders[best_index],
        candidate_results=result.candidate_results,
        candidate_orders=result.candidate_orders,
        criterion_values=values.tolist(),
        selection_criterion=criterion,
        search_method=result.search_method,
        n_attempted=result.n_attempted,
        best_seasonal_order=seasonal,
        candidate_seasonal_orders=result.candidate_seasonal_orders,
        search_messages=result.search_messages,
    )


def _rdl_specs(config: RDLConfig | AutoRDLConfig) -> dict[str, RationalLagSpec]:
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
    """拟合固定传递函数加 SARIMAX 误差的 RDL 模型。"""
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


def fit_auto_rdl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: AutoRDLConfig,
) -> AutoModelResult:
    """仅自动搜索 RDL 的 SARIMAX 误差阶数，传递函数保持固定。"""
    error = config.error
    model = AutoSARIMAX(
        series,
        p=error.p,
        d=error.d,
        q=error.q,
        P=error.P,
        D=error.D,
        Q=error.Q,
        s=error.s,
        trend=error.trend,
        criterion=error.criterion,
        exog=exog,
        log=error.log,
        fit_method=error.fit_method,
        maxiter=error.maxiter,
        cov_type=error.cov_type,
        enforce_stationarity=error.enforce_stationarity,
        enforce_invertibility=error.enforce_invertibility,
        distributed_lags=_rdl_specs(config),
        enforce_distributed_lag_stability=config.enforce_distributed_lag_stability,
    )
    return model.fit()


def fit_ardl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: ARDLConfig,
):
    """拟合标准 ARDL，而非把 SARIMAX AR 误差误称为 ARDL。"""
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
) -> AutoARDLResult:
    """按 AIC/BIC 自动选择标准 ARDL 的目标和逐输入滞后。"""
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
    return model.fit(cov_type=config.cov_type)


def fit_dynamic_model(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
):
    """按模型族和配置方式分发到 Ts 的唯一拟合入口。"""
    if isinstance(config, SARIMAXConfig):
        return fit_sarimax(series, exog, config)
    if isinstance(config, AutoSARIMAXConfig):
        return fit_auto_sarimax(series, exog, config)
    if exog is None:
        raise ValueError("RDL/ARDL 需要解释变量")
    if isinstance(config, RDLConfig):
        return fit_rdl(series, exog, config)
    if isinstance(config, AutoRDLConfig):
        return fit_auto_rdl(series, exog, config)
    if isinstance(config, ARDLConfig):
        return fit_ardl(series, exog, config)
    if isinstance(config, AutoARDLConfig):
        return fit_auto_ardl(series, exog, config)
    raise TypeError(f"不支持的动态回归配置：{type(config)!r}")


def run_residual_diagnostics(
    result: Any,
    lags: int = 10,
) -> pd.DataFrame:
    """对拟合结果执行残差诊断，返回结构化结果表。"""
    tests = result.test_residuals(lags=lags)
    rows = []
    for attribute, label in _DIAGNOSTIC_ROWS:
        item = getattr(tests, attribute)
        pvalue = float(item.pvalue)
        rows.append(
            {
                "检验": label,
                "统计量": float(item.statistic),
                "P值": pvalue,
                "结论": "拒绝原假设" if pvalue < 0.05 else "不拒绝原假设",
            }
        )
    return pd.DataFrame(rows, columns=["检验", "统计量", "P值", "结论"])


def recommended_residual_diagnostic_lags(nobs: int) -> int:
    """按有效残差数给出残差检验的建议最大滞后阶数。

    与 Ts 诊断图一致，使用 ``min(10, floor(n / 5))``；最小值为 1。
    该上限也为 Engle LM 辅助回归保留足够有效样本。
    """
    if nobs < 4:
        raise ValueError("有效残差至少需要 4 个才能执行残差诊断")
    return min(10, max(1, nobs // 5))


def future_dates(result: Any, steps: int) -> pd.DatetimeIndex | None:
    """基于拟合日期频率推算未来预测日期；无法推断时返回 None。"""
    dates = result.dates
    if dates is None or len(dates) == 0:
        return None
    freq = dates.freq
    if freq is None:
        freq = pd.infer_freq(dates)
    if freq is None:
        return None
    offset = pd.tseries.frequencies.to_offset(freq)
    return pd.date_range(
        start=dates[-1] + offset,
        periods=steps,
        freq=offset,
    )


def produce_forecast(
    result: Any,
    start: int | str | pd.Timestamp,
    end: int | str | pd.Timestamp,
    alpha: float = 0.05,
    dynamic: bool = False,
    future_exog: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """对拟合结果预测，返回均值/区间/日期结构。

    Parameters
    ----------
    result : SARIMAXResult or compatible result
        已拟合的 Ts 模型结果。
    start : int or datetime-like
        预测起点；遵循 Ts ``predict`` 的位置/日期语义。
    end : int or datetime-like
        预测终点，包含该位置。
    alpha : float, default=0.05
        预测区间显著性水平。
    dynamic : bool, default=False
        传递给 Ts ``predict`` 的动态预测控制。
    future_exog : pandas.DataFrame or None, optional
        从拟合样本末期到 ``end`` 的完整未来外生变量路径。

    Returns
    -------
    dict
        包含 ``mean``、``lower``、``upper``、``dates``、``steps``、``start``、
        ``end`` 和 ``alpha`` 的预测结构。
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha 必须在 (0, 1) 区间内")

    prediction = result.predict(
        start=start,
        end=end,
        dynamic=dynamic,
        alpha=alpha,
        future_exog=future_exog,
    )
    mean = np.asarray(prediction.mean, dtype=float)
    lower = np.asarray(prediction.lower, dtype=float)
    upper = np.asarray(prediction.upper, dtype=float)
    steps = len(mean)
    return {
        "mean": mean,
        "lower": lower,
        "upper": upper,
        "dates": _prediction_dates(result, start, end, steps),
        "steps": steps,
        "start": start,
        "end": end,
        "alpha": alpha,
    }


def _prediction_dates(
    result: Any,
    start: int | str | pd.Timestamp | None,
    end: int | str | pd.Timestamp | None,
    length: int,
) -> pd.DatetimeIndex | None:
    """按 Ts 预测窗口位置还原结果日期。"""
    dates = result.dates
    if dates is None:
        return None
    dates = pd.DatetimeIndex(dates)
    if isinstance(start, (int, np.integer)) and (
        end is None or isinstance(end, (int, np.integer))
    ):
        start_pos = int(start)
        end_pos = start_pos + length - 1 if end is None else int(end)
        if end_pos < len(dates):
            return dates[start_pos : end_pos + 1]
        future = future_dates(result, end_pos - len(dates) + 1)
        if future is None:
            return None
        calendar = dates.append(future)
        return calendar[start_pos : end_pos + 1]

    frequency = dates.freq or pd.infer_freq(dates)
    if frequency is None:
        return None
    offset = pd.tseries.frequencies.to_offset(frequency)
    start_date = dates[0] if start is None else pd.Timestamp(start)
    end_date = (
        start_date + (length - 1) * offset
        if end is None
        else pd.Timestamp(end)
    )
    calendar = pd.date_range(
        start=dates[0],
        end=max(end_date, dates[-1]),
        freq=offset,
    )
    selection = calendar[(calendar >= start_date) & (calendar <= end_date)]
    return pd.DatetimeIndex(selection[:length])


def build_prediction_table(forecast: dict[str, Any]) -> pd.DataFrame:
    """把预测结构转换为可展示、可下载的表格。"""
    mean = np.asarray(forecast["mean"], dtype=float)
    lower = np.asarray(forecast["lower"], dtype=float)
    upper = np.asarray(forecast["upper"], dtype=float)
    dates = forecast.get("dates")
    if dates is not None:
        index = pd.DatetimeIndex(dates)
        index.name = "日期"
    else:
        start = forecast.get("start", 0)
        start = int(start) if isinstance(start, (int, np.integer)) else 0
        index = pd.RangeIndex(
            start + 1,
            start + len(mean) + 1,
            name="期数",
        )
    return pd.DataFrame(
        {
            "预测值": mean,
            "下界": lower,
            "上界": upper,
        },
        index=index,
    )


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
    "future_dates",
    "produce_forecast",
    "run_residual_diagnostics",
    "select_auto_sarimax_result",
    "translate_ts_error",
    "validate_fit_inputs",
]
