"""SARIMAX 模型与自动选阶的配置对象（UI 与逻辑分离）。"""

from __future__ import annotations

from dataclasses import dataclass

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

# UI 友好上限（Ts 包本身只要求非负整数）。
_ORDER_LIMITS = {"p": (0, 6), "q": (0, 6), "d": (0, 2)}
_SEASONAL_LIMITS = {"P": (0, 3), "Q": (0, 3), "D": (0, 2), "s": (0, 12)}
_RANGE_LIMITS = {"p": (0, 6), "q": (0, 6), "d": (0, 2),
                 "P": (0, 3), "Q": (0, 3), "D": (0, 2)}


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


@dataclass(frozen=True)
class SARIMAXConfig:
    """手动 SARIMAX 拟合配置。"""

    order: tuple[int, int, int] = (1, 0, 0)
    seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0)
    trend: str = "c"
    log: bool = False
    enforce_stationarity: bool = True
    enforce_invertibility: bool = True
    fit_method: str = "bfgs"
    maxiter: int = 500
    cov_type: str = "oim"

    def __post_init__(self) -> None:
        if not isinstance(self.order, (tuple, list)) or len(self.order) != 3:
            raise ValueError("order 必须是 (p, d, q) 三元组")
        p, d, q = self.order
        object.__setattr__(
            self,
            "order",
            (
                _validate_int_in_range("p", p, _ORDER_LIMITS["p"]),
                _validate_int_in_range("d", d, _ORDER_LIMITS["d"]),
                _validate_int_in_range("q", q, _ORDER_LIMITS["q"]),
            ),
        )
        if not isinstance(self.seasonal_order, (tuple, list)) or len(
            self.seasonal_order
        ) != 4:
            raise ValueError("seasonal_order 必须是 (P, D, Q, s) 四元组")
        P, D, Q, s = self.seasonal_order
        object.__setattr__(
            self,
            "seasonal_order",
            (
                _validate_int_in_range("P", P, _SEASONAL_LIMITS["P"]),
                _validate_int_in_range("D", D, _SEASONAL_LIMITS["D"]),
                _validate_int_in_range("Q", Q, _SEASONAL_LIMITS["Q"]),
                _validate_int_in_range("s", s, _SEASONAL_LIMITS["s"]),
            ),
        )
        object.__setattr__(self, "trend", _validate_trend(self.trend))
        for name, value in (
            ("log", self.log),
            ("enforce_stationarity", self.enforce_stationarity),
            ("enforce_invertibility", self.enforce_invertibility),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} 必须是布尔值")
        if self.fit_method not in SARIMAX_OPTIMIZERS:
            raise ValueError(
                f"fit_method 必须是 {SARIMAX_OPTIMIZERS} 之一，"
                f"got {self.fit_method!r}"
            )
        if self.maxiter < 1:
            raise ValueError("maxiter 必须为正整数")
        if self.cov_type not in SARIMAX_COV_TYPES:
            raise ValueError(
                f"cov_type 必须是 {SARIMAX_COV_TYPES} 之一，"
                f"got {self.cov_type!r}"
            )

    def signature(self) -> tuple:
        """返回用于结果缓存失效的可哈希签名。"""
        return (
            "manual",
            self.order,
            self.seasonal_order,
            self.trend,
            self.log,
            self.enforce_stationarity,
            self.enforce_invertibility,
            self.fit_method,
            self.maxiter,
            self.cov_type,
        )


@dataclass(frozen=True)
class AutoSARIMAXConfig:
    """AutoSARIMAX 网格搜索配置。"""

    p: tuple[int, int] = (0, 3)
    d: tuple[int, int] = (0, 1)
    q: tuple[int, int] = (0, 3)
    P: tuple[int, int] = (0, 1)
    D: tuple[int, int] = (0, 1)
    Q: tuple[int, int] = (0, 1)
    s: int = 0
    trend: str = "c"
    criterion: str = "aic"
    log: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "p", _validate_range("p", self.p))
        object.__setattr__(self, "d", _validate_range("d", self.d))
        object.__setattr__(self, "q", _validate_range("q", self.q))
        object.__setattr__(self, "P", _validate_range("P", self.P))
        object.__setattr__(self, "D", _validate_range("D", self.D))
        object.__setattr__(self, "Q", _validate_range("Q", self.Q))
        object.__setattr__(
            self,
            "s",
            _validate_int_in_range("s", self.s, _SEASONAL_LIMITS["s"]),
        )
        object.__setattr__(self, "trend", _validate_trend(self.trend))
        if self.criterion not in AUTO_CRITERIA:
            raise ValueError(
                f"criterion 必须是 {AUTO_CRITERIA} 之一，got {self.criterion!r}"
            )
        if not isinstance(self.log, bool):
            raise TypeError("log 必须是布尔值")

    def candidate_count(self) -> int:
        """返回网格搜索将尝试的模型组合数。"""
        p_lo, p_hi = self.p
        d_lo, d_hi = self.d
        q_lo, q_hi = self.q
        count = (p_hi - p_lo + 1) * (d_hi - d_lo + 1) * (q_hi - q_lo + 1)
        if self.s > 0:
            P_lo, P_hi = self.P
            D_lo, D_hi = self.D
            Q_lo, Q_hi = self.Q
            count *= (P_hi - P_lo + 1) * (D_hi - D_lo + 1) * (Q_hi - Q_lo + 1)
        return count

    def signature(self) -> tuple:
        """返回用于结果缓存失效的可哈希签名。"""
        return (
            "auto",
            self.p,
            self.d,
            self.q,
            self.P,
            self.D,
            self.Q,
            self.s,
            self.trend,
            self.criterion,
            self.log,
        )


__all__ = [
    "AUTO_CRITERIA",
    "AutoSARIMAXConfig",
    "SARIMAXConfig",
    "SARIMAX_COV_TYPES",
    "SARIMAX_OPTIMIZERS",
    "TREND_LABELS",
    "TREND_OPTIONS",
]
