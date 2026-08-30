"""标准 ARDL 手动与自动选阶配置。"""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.models.SARIMAX.core.config_shared import (
    ARDL_CRITERIA,
    ARDL_SEARCH_METHODS,
    _validate_int_in_range,
    _validate_lag_tuple,
    _validate_trend,
)


def _validate_ardl_lags(
    name: str,
    value: object,
    *,
    allow_none: bool,
) -> int | tuple[int, ...] | None:
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
    normalized = _validate_lag_tuple(
        name,
        value,
        minimum=0,
        allow_empty=allow_none,
    )
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
        normalized.append(
            (name, _validate_ardl_lags(name, order, allow_none=False))
        )
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
        object.__setattr__(
            self,
            "lags",
            _validate_ardl_lags("目标滞后", self.lags, allow_none=True),
        )
        object.__setattr__(
            self,
            "input_orders",
            _validate_ardl_orders(self.input_orders),
        )
        object.__setattr__(self, "trend", _validate_trend(self.trend))
        for name in ("causal", "seasonal", "log"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} 必须是布尔值")
        if self.period is not None:
            object.__setattr__(
                self,
                "period",
                _validate_int_in_range("period", self.period, (2, 365)),
            )
        if self.seasonal and self.period is None:
            raise ValueError("启用季节虚拟项时必须设置 period")
        if self.hold_back is not None:
            object.__setattr__(
                self,
                "hold_back",
                _validate_int_in_range(
                    "hold_back",
                    self.hold_back,
                    (0, 100000),
                ),
            )

    def order_mapping(self) -> dict[str, int | tuple[int, ...] | None]:
        """返回 Ts/Statsmodels 所需的逐输入滞后映射。"""
        return dict(self.input_orders)

    def signature(self) -> tuple:
        """返回完整 ARDL 缓存签名。"""
        return (
            "ardl-manual",
            self.lags,
            self.input_orders,
            self.trend,
            self.causal,
            self.seasonal,
            self.period,
            self.hold_back,
            self.log,
            self.cov_type,
        )


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
        object.__setattr__(
            self,
            "maxlag",
            _validate_int_in_range("最大目标滞后", self.maxlag, (0, 12)),
        )
        pairs = _validate_ardl_orders(self.max_input_orders)
        if any(not isinstance(order, int) for _, order in pairs):
            raise TypeError("自动 ARDL 的最大输入滞后必须是整数")
        object.__setattr__(
            self,
            "max_input_orders",
            tuple((name, int(order)) for name, order in pairs),
        )
        object.__setattr__(self, "trend", _validate_trend(self.trend))
        if self.criterion not in ARDL_CRITERIA:
            raise ValueError(f"criterion 必须是 {ARDL_CRITERIA} 之一")
        if self.search_method not in ARDL_SEARCH_METHODS:
            raise ValueError(
                f"search_method 必须是 {ARDL_SEARCH_METHODS} 之一"
            )
        for name in ("causal", "seasonal", "log"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} 必须是布尔值")
        if self.period is not None:
            object.__setattr__(
                self,
                "period",
                _validate_int_in_range("period", self.period, (2, 365)),
            )
        if self.seasonal and self.period is None:
            raise ValueError("启用季节虚拟项时必须设置 period")
        if self.hold_back is not None:
            object.__setattr__(
                self,
                "hold_back",
                _validate_int_in_range(
                    "hold_back",
                    self.hold_back,
                    (0, 100000),
                ),
            )

    def maxorder_mapping(self) -> dict[str, int]:
        """返回自动 ARDL 的逐输入最大滞后映射。"""
        return dict(self.max_input_orders)

    def signature(self) -> tuple:
        """返回完整自动 ARDL 缓存签名。"""
        return (
            "ardl-auto",
            self.maxlag,
            self.max_input_orders,
            self.trend,
            self.criterion,
            self.search_method,
            self.causal,
            self.seasonal,
            self.period,
            self.hold_back,
            self.log,
            self.cov_type,
        )


__all__ = ["ARDLConfig", "AutoARDLConfig"]
