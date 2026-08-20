"""SARIMAX 拟合、诊断与预测编排（唯一调用 Ts 包的模块，无 streamlit 依赖）。"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from Ts.TsModels import AutoModelResult, AutoSARIMAX, SARIMAX, SARIMAXResult

from dashboard.models.SARIMAX.core.model_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)

logger = logging.getLogger(__name__)

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


def validate_fit_inputs(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: SARIMAXConfig | AutoSARIMAXConfig,
) -> list[str]:
    """拟合前预检，返回用户可读的问题列表；空列表表示可以拟合。"""
    problems: list[str] = []
    if series is None:
        problems.append("尚未选择目标变量")
        return problems

    valid = series.dropna()
    if len(valid) < MIN_OBSERVATIONS:
        problems.append(
            f"样本量不足：有效观测 {len(valid)} 个，SARIMAX 至少需要 "
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

    seasonal_period = (
        config.seasonal_order[3] if isinstance(config, SARIMAXConfig) else config.s
    )
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
    )
    return model.fit()


def run_residual_diagnostics(
    result: SARIMAXResult,
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


def future_dates(result: SARIMAXResult, steps: int) -> pd.DatetimeIndex | None:
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
    result: SARIMAXResult,
    steps: int,
    alpha: float = 0.05,
    dynamic: bool = False,
    future_exog: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """对拟合结果做样本外预测，返回均值/区间/日期结构。"""
    steps = int(steps)
    if steps <= 0:
        raise ValueError("预测期数必须为正整数")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha 必须在 (0, 1) 区间内")

    start = result.nobs
    end = result.nobs + steps - 1
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
    return {
        "mean": mean,
        "lower": lower,
        "upper": upper,
        "dates": future_dates(result, steps),
        "steps": steps,
        "alpha": alpha,
    }


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
        index = pd.RangeIndex(1, len(mean) + 1, name="期数")
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
    "build_prediction_table",
    "fit_auto_sarimax",
    "fit_sarimax",
    "future_dates",
    "produce_forecast",
    "run_residual_diagnostics",
    "translate_ts_error",
    "validate_fit_inputs",
]
