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
ARDL_CRITERIA = ("aic", "bic")
ARDL_SEARCH_METHODS = ("hierarchical", "global")
RDL_INITIALIZATIONS = ("auto", "zero", "steady_state")

# UI 友好上限（Ts 包本身只要求非负整数）。
_ORDER_LIMITS = {"p": (0, 6), "q": (0, 6), "d": (0, 2)}
_SEASONAL_LIMITS = {"P": (0, 3), "Q": (0, 3), "D": (0, 2), "s": (0, 12)}
_RANGE_LIMITS = {"p": (0, 6), "q": (0, 6), "d": (0, 2),
                 "P": (0, 3), "Q": (0, 3), "D": (0, 2)}
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
    enforce_stationarity: bool = True
    enforce_invertibility: bool = True

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


@dataclass(frozen=True)
class RDLInputConfig:
    """单个 RDL 输入的传递函数设置。"""

    name: str
    numerator_order: int = 0
    denominator_order: int = 0
    delay: int = 0
    numerator_lags: tuple[int, ...] | None = None
    denominator_lags: tuple[int, ...] | None = None
    initialization: str = "auto"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("RDL 输入变量名不能为空")
        object.__setattr__(
            self, "numerator_order", _validate_int_in_range(
                "RDL 分子阶数", self.numerator_order, (0, 12)
            )
        )
        object.__setattr__(
            self, "denominator_order", _validate_int_in_range(
                "RDL 分母阶数", self.denominator_order, (0, 12)
            )
        )
        object.__setattr__(
            self, "delay", _validate_int_in_range("RDL 延迟", self.delay, (0, 24))
        )
        object.__setattr__(
            self, "numerator_lags", _validate_lag_tuple(
                "RDL 分子稀疏滞后", self.numerator_lags,
                minimum=0, allow_empty=False,
            )
        )
        object.__setattr__(
            self, "denominator_lags", _validate_lag_tuple(
                "RDL 分母稀疏滞后", self.denominator_lags,
                minimum=1, allow_empty=True,
            )
        )
        if self.initialization not in RDL_INITIALIZATIONS:
            raise ValueError(f"initialization 必须是 {RDL_INITIALIZATIONS} 之一")

    def specification(self) -> tuple[object, object, int, str]:
        """返回供 ``RationalLagSpec`` 使用的规范化参数。"""
        numerator = (
            self.numerator_lags
            if self.numerator_lags is not None
            else self.numerator_order
        )
        denominator = (
            self.denominator_lags
            if self.denominator_lags is not None
            else self.denominator_order
        )
        return numerator, denominator, self.delay, self.initialization

    def signature(self) -> tuple:
        """返回可哈希的传递函数签名。"""
        return (
            self.name,
            self.numerator_order,
            self.denominator_order,
            self.delay,
            self.numerator_lags,
            self.denominator_lags,
            self.initialization,
        )


def _validate_rdl_inputs(inputs: tuple[RDLInputConfig, ...]) -> tuple[RDLInputConfig, ...]:
    if not isinstance(inputs, (tuple, list)) or not inputs:
        raise ValueError("RDL 至少需要选择一个解释变量")
    normalized = tuple(inputs)
    if not all(isinstance(item, RDLInputConfig) for item in normalized):
        raise TypeError("inputs 必须由 RDLInputConfig 组成")
    names = [item.name for item in normalized]
    if len(names) != len(set(names)):
        raise ValueError("RDL 输入变量不能重复")
    return normalized


@dataclass(frozen=True)
class RDLConfig:
    """手动 RDL：固定传递函数结构与 SARIMAX 误差项。"""

    inputs: tuple[RDLInputConfig, ...]
    error: SARIMAXConfig = SARIMAXConfig()
    enforce_distributed_lag_stability: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", _validate_rdl_inputs(self.inputs))
        if not isinstance(self.error, SARIMAXConfig):
            raise TypeError("error 必须是 SARIMAXConfig")
        if not isinstance(self.enforce_distributed_lag_stability, bool):
            raise TypeError("enforce_distributed_lag_stability 必须是布尔值")

    @property
    def log(self) -> bool:
        """沿用 SARIMAX 误差模型的响应变换设置。"""
        return self.error.log

    def signature(self) -> tuple:
        """返回 RDL 配置的完整缓存签名。"""
        return (
            "rdl-manual",
            self.error.signature(),
            tuple(item.signature() for item in self.inputs),
            self.enforce_distributed_lag_stability,
        )


@dataclass(frozen=True)
class AutoRDLConfig:
    """自动选择 SARIMAX 误差阶数的 RDL 配置。"""

    inputs: tuple[RDLInputConfig, ...]
    error: AutoSARIMAXConfig = AutoSARIMAXConfig()
    enforce_distributed_lag_stability: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", _validate_rdl_inputs(self.inputs))
        if not isinstance(self.error, AutoSARIMAXConfig):
            raise TypeError("error 必须是 AutoSARIMAXConfig")
        if not isinstance(self.enforce_distributed_lag_stability, bool):
            raise TypeError("enforce_distributed_lag_stability 必须是布尔值")

    @property
    def log(self) -> bool:
        """沿用自动 SARIMAX 误差模型的响应变换设置。"""
        return self.error.log

    def signature(self) -> tuple:
        """返回自动 RDL 配置的完整缓存签名。"""
        return (
            "rdl-auto",
            self.error.signature(),
            tuple(item.signature() for item in self.inputs),
            self.enforce_distributed_lag_stability,
        )


def _validate_ardl_lags(name: str, value: object, *, allow_none: bool) -> int | tuple[int, ...] | None:
    if value is None:
        if allow_none:
            return None
        raise TypeError(f"{name} 不能为 None")
    if isinstance(value, bool):
        raise TypeError(f"{name} 必须是非负整数或滞后列表")
    if isinstance(value, int):
        if value < 0 or value > 12:
            raise ValueError(f"{name} 必须在 0–12 之间")
        return value
    normalized = _validate_lag_tuple(name, value, minimum=0, allow_empty=allow_none)
    return normalized


def _validate_ardl_orders(
    orders: tuple[tuple[str, object], ...],
) -> tuple[tuple[str, int | tuple[int, ...] | None], ...]:
    if not isinstance(orders, (tuple, list)) or not orders:
        raise ValueError("ARDL 至少需要选择一个解释变量")
    normalized = []
    for item in orders:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("逐变量输入阶数必须是 (变量名, 阶数) 二元组")
        name, order = item
        if not isinstance(name, str) or not name:
            raise ValueError("ARDL 输入变量名不能为空")
        normalized.append((name, _validate_ardl_lags(name, order, allow_none=False)))
    names = [name for name, _ in normalized]
    if len(names) != len(set(names)):
        raise ValueError("ARDL 输入变量不能重复")
    return tuple(normalized)


@dataclass(frozen=True)
class ARDLConfig:
    """手动标准 ARDL 配置（目标滞后与逐输入有限滞后）。"""

    lags: int | tuple[int, ...] | None = 1
    input_orders: tuple[tuple[str, object], ...] = ()
    trend: str = "c"
    causal: bool = False
    seasonal: bool = False
    period: int | None = None
    hold_back: int | None = None
    log: bool = False
    cov_type: str = "nonrobust"

    def __post_init__(self) -> None:
        object.__setattr__(self, "lags", _validate_ardl_lags("目标滞后", self.lags, allow_none=True))
        object.__setattr__(self, "input_orders", _validate_ardl_orders(self.input_orders))
        object.__setattr__(self, "trend", _validate_trend(self.trend))
        for name in ("causal", "seasonal", "log"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} 必须是布尔值")
        if self.period is not None:
            object.__setattr__(self, "period", _validate_int_in_range("period", self.period, (2, 365)))
        if self.seasonal and self.period is None:
            raise ValueError("启用季节虚拟项时必须设置 period")
        if self.hold_back is not None:
            object.__setattr__(self, "hold_back", _validate_int_in_range("hold_back", self.hold_back, (0, 100000)))

    def order_mapping(self) -> dict[str, int | tuple[int, ...] | None]:
        """返回 Ts/Statsmodels 所需的逐输入滞后映射。"""
        return dict(self.input_orders)

    def signature(self) -> tuple:
        """返回完整 ARDL 缓存签名。"""
        return ("ardl-manual", self.lags, self.input_orders, self.trend, self.causal, self.seasonal, self.period, self.hold_back, self.log, self.cov_type)


@dataclass(frozen=True)
class AutoARDLConfig:
    """自动标准 ARDL 选阶配置。"""

    maxlag: int = 3
    max_input_orders: tuple[tuple[str, int], ...] = ()
    trend: str = "c"
    criterion: str = "bic"
    search_method: str = "hierarchical"
    causal: bool = False
    seasonal: bool = False
    period: int | None = None
    hold_back: int | None = None
    log: bool = False
    cov_type: str = "nonrobust"

    def __post_init__(self) -> None:
        object.__setattr__(self, "maxlag", _validate_int_in_range("最大目标滞后", self.maxlag, (0, 12)))
        pairs = _validate_ardl_orders(self.max_input_orders)
        if any(not isinstance(order, int) for _, order in pairs):
            raise TypeError("自动 ARDL 的最大输入滞后必须是整数")
        object.__setattr__(self, "max_input_orders", tuple((name, int(order)) for name, order in pairs))
        object.__setattr__(self, "trend", _validate_trend(self.trend))
        if self.criterion not in ARDL_CRITERIA:
            raise ValueError(f"criterion 必须是 {ARDL_CRITERIA} 之一")
        if self.search_method not in ARDL_SEARCH_METHODS:
            raise ValueError(f"search_method 必须是 {ARDL_SEARCH_METHODS} 之一")
        for name in ("causal", "seasonal", "log"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} 必须是布尔值")
        if self.period is not None:
            object.__setattr__(self, "period", _validate_int_in_range("period", self.period, (2, 365)))
        if self.seasonal and self.period is None:
            raise ValueError("启用季节虚拟项时必须设置 period")
        if self.hold_back is not None:
            object.__setattr__(self, "hold_back", _validate_int_in_range("hold_back", self.hold_back, (0, 100000)))

    def maxorder_mapping(self) -> dict[str, int]:
        """返回自动 ARDL 的逐输入最大滞后映射。"""
        return dict(self.max_input_orders)

    def signature(self) -> tuple:
        """返回完整自动 ARDL 缓存签名。"""
        return ("ardl-auto", self.maxlag, self.max_input_orders, self.trend, self.criterion, self.search_method, self.causal, self.seasonal, self.period, self.hold_back, self.log, self.cov_type)


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
    "ARDLConfig",
    "AutoARDLConfig",
    "AutoRDLConfig",
    "AutoSARIMAXConfig",
    "RDLConfig",
    "RDLInputConfig",
    "SARIMAXConfig",
]
