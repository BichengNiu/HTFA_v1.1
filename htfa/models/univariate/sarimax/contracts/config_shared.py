"""动态回归配置 module 共用的常量与校验函数。"""

from __future__ import annotations

TREND_OPTIONS = ("n", "c", "t", "ct")
TREND_LABELS = {
    "n": "无趋势",
    "c": "常数项",
    "t": "线性趋势",
    "ct": "常数 + 线性趋势",
}
SARIMAX_OPTIMIZERS = (
    "basinhopping",
    "bfgs",
    "cg",
    "lbfgs",
    "ncg",
    "newton",
    "nm",
    "powell",
)
SARIMAX_COV_TYPES = ("approx", "oim", "opg", "robust", "robust_approx")
AUTO_CRITERIA = ("aic", "bic", "hqic", "aicc")
ARDL_CRITERIA = ("aic", "bic")
ARDL_SEARCH_METHODS = ("hierarchical", "global")
RDL_INITIALIZATIONS = ("auto", "zero", "steady_state")

# UI 友好上限（Ts 包本身只要求非负整数）。
_ORDER_LIMITS = {"p": (0, 6), "q": (0, 6), "d": (0, 2)}
_SEASONAL_LIMITS = {"P": (0, 3), "Q": (0, 3), "D": (0, 2), "s": (0, 365)}
_RANGE_LIMITS = {
    "p": (0, 6),
    "q": (0, 6),
    "d": (0, 2),
    "P": (0, 3),
    "Q": (0, 3),
    "D": (0, 2),
}
SARIMAX_RANGE_LIMITS = _RANGE_LIMITS.copy()


def _validate_trend(trend: str) -> str:
    if trend not in TREND_OPTIONS:
        raise ValueError(f"trend 必须是 {TREND_OPTIONS} 之一，got {trend!r}")
    return trend


def _validate_int_in_range(name: str, value: int, limits: tuple[int, int]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} 必须是整数")
    low, high = limits
    if not low <= value <= high:
        raise ValueError(f"{name} 必须在 {low}–{high} 之间")
    return value


def _validate_range(name: str, value: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} 必须是 (最小值, 最大值) 二元组")
    low, high = value
    low = _validate_int_in_range(f"{name} 下限", low, _RANGE_LIMITS[name])
    high = _validate_int_in_range(f"{name} 上限", high, _RANGE_LIMITS[name])
    if low > high:
        raise ValueError(f"{name} 下限不能大于上限")
    return (low, high)


def _validate_lag_tuple(
    name: str,
    values: tuple[int, ...] | None,
    *,
    minimum: int,
    allow_empty: bool,
) -> tuple[int, ...] | None:
    """规范化可选的稀疏滞后列表。"""
    if values is None:
        return None
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{name} 必须是整数滞后列表")
    normalized = tuple(sorted(set(values)))
    if not normalized and not allow_empty:
        raise ValueError(f"{name} 至少需要一个滞后")
    for lag in normalized:
        if isinstance(lag, bool) or not isinstance(lag, int) or lag < minimum:
            raise ValueError(f"{name} 必须包含不小于 {minimum} 的整数")
    return normalized


__all__ = [
    "ARDL_CRITERIA",
    "ARDL_SEARCH_METHODS",
    "AUTO_CRITERIA",
    "RDL_INITIALIZATIONS",
    "SARIMAX_COV_TYPES",
    "SARIMAX_OPTIMIZERS",
    "SARIMAX_RANGE_LIMITS",
    "TREND_LABELS",
    "TREND_OPTIONS",
    "_ORDER_LIMITS",
    "_SEASONAL_LIMITS",
    "_validate_int_in_range",
    "_validate_lag_tuple",
    "_validate_range",
    "_validate_trend",
]
