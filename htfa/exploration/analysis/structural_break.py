"""使用 TsTests 执行结构突变检验。"""

from __future__ import annotations

import pandas as pd
from Ts.TsTests import ZivotAndrewsTest

from htfa.exploration.core.constants import MIN_SAMPLES_ADF
from htfa.exploration.core.validation import validate_real_series

STRUCTURAL_BREAK_MODELS = {
    "intercept": "截距突变",
    "slope": "趋势斜率突变",
    "both": "截距与趋势斜率同时突变",
}


STRUCTURAL_BREAK_LAG_METHODS = {
    "tstat": "t 统计量逐步选择",
    "aic": "AIC",
    "bic": "BIC",
}


STRUCTURAL_BREAK_RESULT_COLUMNS = [
    "检验",
    "突变形式",
    "滞后选择",
    "原假设",
    "统计量",
    "临界值",
    "滞后阶数",
    "有效样本数",
    "判定",
    "平稳性解释",
    "结构突变点",
]


def _prepare_series(series: pd.Series) -> pd.Series:
    values = validate_real_series(series, dropna=True)
    if len(values) < MIN_SAMPLES_ADF:
        raise ValueError(
            f"结构突变检验至少需要 {MIN_SAMPLES_ADF} 个有效观测"
        )
    if values.nunique() <= 1:
        raise ValueError("常数序列无法进行结构突变检验")
    return values


def run_zivot_andrews_test(
    series: pd.Series,
    *,
    alpha: float = 0.05,
    model: str = "intercept",
    lag_method: str = "tstat",
) -> pd.DataFrame:
    """运行允许一个未知内生突变点的 Zivot–Andrews 检验。"""
    if model not in STRUCTURAL_BREAK_MODELS:
        raise ValueError(
            "突变形式必须是 intercept、slope 或 both"
        )
    if lag_method not in STRUCTURAL_BREAK_LAG_METHODS:
        raise ValueError("滞后选择必须是 tstat、aic 或 bic")
    alpha_key = {
        0.01: "cv_01",
        0.05: "cv_05",
        0.10: "cv_10",
    }.get(round(float(alpha), 2))
    if alpha_key is None:
        raise ValueError("显著性水平只能是 1%、5% 或 10%")

    values = _prepare_series(series)
    test = ZivotAndrewsTest(
        values,
        model=model,
        max_lags=min(8, max(1, len(values) // 5)),
        lag_method=lag_method,
    )
    result = test.fit()
    critical_value = float(getattr(result, alpha_key))
    reject = float(result.statistic) < critical_value
    break_index = int(result.break_index)
    break_point = (
        values.index[break_index]
        if 0 <= break_index < len(values)
        else None
    )

    row = {
        "检验": "Zivot–Andrews 结构突变检验",
        "突变形式": STRUCTURAL_BREAK_MODELS[model],
        "滞后选择": STRUCTURAL_BREAK_LAG_METHODS[lag_method],
        "原假设": "允许一个未知结构突变时，序列仍存在单位根",
        "统计量": float(result.statistic),
        "临界值": critical_value,
        "滞后阶数": int(result.lags),
        "有效样本数": int(result.nobs),
        "判定": "拒绝原假设" if reject else "不能拒绝原假设",
        "平稳性解释": "支持突变平稳" if reject else "支持存在单位根",
        "结构突变点": break_point,
    }
    return pd.DataFrame([row], columns=STRUCTURAL_BREAK_RESULT_COLUMNS)


__all__ = [
    "STRUCTURAL_BREAK_LAG_METHODS",
    "STRUCTURAL_BREAK_MODELS",
    "STRUCTURAL_BREAK_RESULT_COLUMNS",
    "run_zivot_andrews_test",
]
