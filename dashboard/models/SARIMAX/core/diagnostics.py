"""动态回归拟合结果的残差诊断计算。"""

from __future__ import annotations

from typing import Any

import pandas as pd

_DIAGNOSTIC_ROWS = (
    ("white_noise", "残差自相关（Ljung-Box）"),
    ("normality", "残差正态性（Jarque-Bera）"),
    ("ljung_box", "ARCH 效应（平方残差 Ljung-Box）"),
    ("engle_lm", "ARCH 效应（Engle LM）"),
)


def run_residual_diagnostics(
    result: Any,
    lags: int = 10,
) -> pd.DataFrame:
    """对拟合结果执行残差诊断，返回结构化结果表。

    Parameters
    ----------
    result : object
        提供 ``test_residuals`` 方法的 Ts 拟合结果。
    lags : int, default=10
        残差检验使用的最大滞后阶数。

    Returns
    -------
    pandas.DataFrame
        包含检验名称、统计量、P 值和结论的诊断表。
    """
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

    Parameters
    ----------
    nobs : int
        有效残差观测数，至少为 4。

    Returns
    -------
    int
        与 Ts 诊断图一致的建议滞后阶数，即 ``min(10, floor(n / 5))``，
        最小值为 1。
    """
    if nobs < 4:
        raise ValueError("有效残差至少需要 4 个才能执行残差诊断")
    return min(10, max(1, nobs // 5))


__all__ = ["recommended_residual_diagnostic_lags", "run_residual_diagnostics"]
