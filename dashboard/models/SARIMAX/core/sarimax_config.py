"""SARIMAX 手动与自动选阶配置。"""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.models.SARIMAX.core.config_shared import (
    AUTO_CRITERIA,
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
    _ORDER_LIMITS,
    _SEASONAL_LIMITS,
    _validate_int_in_range,
    _validate_range,
    _validate_trend,
)


@dataclass(frozen=True)
class SARIMAXConfig:
    """手动 SARIMAX 拟合配置。"""

    order: tuple[int, int, int] = (1, 0, 0)
    seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0)
    trend: str = "c"
    log: bool = False
    enforce_stationarity: bool = False
    enforce_invertibility: bool = False
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
        if isinstance(self.maxiter, bool) or not isinstance(self.maxiter, int):
            raise TypeError("maxiter 必须是正整数")
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
    fit_method: str = "bfgs"
    maxiter: int = 500
    cov_type: str = "oim"
    enforce_stationarity: bool = False
    enforce_invertibility: bool = False

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
        if self.fit_method not in SARIMAX_OPTIMIZERS:
            raise ValueError(
                f"fit_method 必须是 {SARIMAX_OPTIMIZERS} 之一，"
                f"got {self.fit_method!r}"
            )
        if isinstance(self.maxiter, bool) or not isinstance(self.maxiter, int):
            raise TypeError("maxiter 必须是正整数")
        if self.maxiter < 1:
            raise ValueError("maxiter 必须为正整数")
        if self.cov_type not in SARIMAX_COV_TYPES:
            raise ValueError(
                f"cov_type 必须是 {SARIMAX_COV_TYPES} 之一，"
                f"got {self.cov_type!r}"
            )
        for name in ("enforce_stationarity", "enforce_invertibility"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} 必须是布尔值")

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
            self.fit_method,
            self.maxiter,
            self.cov_type,
            self.enforce_stationarity,
            self.enforce_invertibility,
        )


__all__ = ["AutoSARIMAXConfig", "SARIMAXConfig"]
