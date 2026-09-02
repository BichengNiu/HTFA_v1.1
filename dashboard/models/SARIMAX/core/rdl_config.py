"""RDL 传递函数及其 SARIMAX 误差配置。"""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.models.SARIMAX.core.config_shared import (
    RDL_INITIALIZATIONS,
    _validate_int_in_range,
    _validate_lag_tuple,
)
from dashboard.models.SARIMAX.core.sarimax_config import SARIMAXConfig


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
            self,
            "numerator_order",
            _validate_int_in_range(
                "RDL 分子阶数", self.numerator_order, (0, 12)
            ),
        )
        object.__setattr__(
            self,
            "denominator_order",
            _validate_int_in_range(
                "RDL 分母阶数", self.denominator_order, (0, 12)
            ),
        )
        object.__setattr__(
            self,
            "delay",
            _validate_int_in_range("RDL 延迟", self.delay, (0, 24)),
        )
        object.__setattr__(
            self,
            "numerator_lags",
            _validate_lag_tuple(
                "RDL 分子稀疏滞后",
                self.numerator_lags,
                minimum=0,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "denominator_lags",
            _validate_lag_tuple(
                "RDL 分母稀疏滞后",
                self.denominator_lags,
                minimum=1,
                allow_empty=True,
            ),
        )
        if self.initialization not in RDL_INITIALIZATIONS:
            raise ValueError(
                f"initialization 必须是 {RDL_INITIALIZATIONS} 之一"
            )

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


def _validate_rdl_inputs(
    inputs: tuple[RDLInputConfig, ...],
) -> tuple[RDLInputConfig, ...]:
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


__all__ = ["RDLConfig", "RDLInputConfig"]
