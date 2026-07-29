"""阿联酋增长诊断的纯计算函数。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AdditivityResult:
    """总量与分项的可加总性检查。"""

    residual: pd.Series
    residual_ratio: pd.Series
    within_tolerance: pd.Series


@dataclass(frozen=True)
class ContributionResult:
    """增长率及分项贡献。"""

    total_growth: pd.Series
    contributions: pd.DataFrame
    additivity: AdditivityResult
    periods: int


@dataclass(frozen=True)
class NominalRealBridge:
    """名义增长、实际增长和价格变化的对数桥接。"""

    deflator: pd.Series
    nominal_log_growth: pd.Series
    real_log_growth: pd.Series
    deflator_log_growth: pd.Series
    periods: int


def _validate_series(series: pd.Series, label: str) -> None:
    if series.index.has_duplicates:
        raise ValueError(f"{label}包含重复时期")
    if not series.index.is_monotonic_increasing:
        raise ValueError(f"{label}的时间索引必须递增")


def _align_components(
    total: pd.Series,
    components: Mapping[str, pd.Series],
) -> tuple[pd.Series, pd.DataFrame]:
    _validate_series(total, total.name or "总量")
    if not components:
        raise ValueError("至少需要一个分项")

    frames = [total.rename("__total__")]
    for label, series in components.items():
        _validate_series(series, label)
        frames.append(series.rename(label))
    aligned = pd.concat(frames, axis=1, join="inner").sort_index()
    if aligned.empty:
        raise ValueError("总量与分项没有共同观测期")
    return aligned.pop("__total__"), aligned


def validate_additivity(
    total: pd.Series,
    components: Mapping[str, pd.Series],
    *,
    absolute_tolerance: float = 1e-6,
    relative_tolerance: float = 0.005,
) -> AdditivityResult:
    """检查分项是否与总量相加一致，保留残差而非分摊。"""

    aligned_total, aligned_components = _align_components(total, components)
    component_sum = aligned_components.sum(axis=1, min_count=1)
    residual = (aligned_total - component_sum).rename("residual")
    denominator = aligned_total.abs().replace(0.0, np.nan)
    residual_ratio = (residual.abs() / denominator).rename("residual_ratio")
    within_tolerance = (
        (residual.abs() <= absolute_tolerance)
        | (residual_ratio <= relative_tolerance)
    ).rename("within_tolerance")
    return AdditivityResult(
        residual=residual,
        residual_ratio=residual_ratio,
        within_tolerance=within_tolerance,
    )


def calculate_growth_contributions(
    total: pd.Series,
    components: Mapping[str, pd.Series],
    *,
    periods: int,
    absolute_tolerance: float = 1e-6,
    relative_tolerance: float = 0.005,
) -> ContributionResult:
    """计算同比或环比分项增长贡献，单位为百分点。"""

    if periods <= 0:
        raise ValueError("比较期数必须为正整数")
    aligned_total, aligned_components = _align_components(total, components)
    lagged_total = aligned_total.shift(periods)
    if (lagged_total.dropna() <= 0).any():
        raise ValueError("滞后总量必须为正，无法计算增长贡献")

    total_growth = (
        (aligned_total - lagged_total) / lagged_total * 100
    ).rename("total_growth")
    contributions = (
        aligned_components - aligned_components.shift(periods)
    ).div(lagged_total, axis=0) * 100
    additivity = validate_additivity(
        aligned_total,
        {
            column: aligned_components[column]
            for column in aligned_components.columns
        },
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    return ContributionResult(
        total_growth=total_growth,
        contributions=contributions,
        additivity=additivity,
        periods=periods,
    )


def calculate_nominal_real_bridge(
    nominal: pd.Series,
    real: pd.Series,
    *,
    periods: int,
) -> NominalRealBridge:
    """以对数差分精确拆解名义增长为实际增长和价格变化。"""

    if periods <= 0:
        raise ValueError("比较期数必须为正整数")
    _validate_series(nominal, nominal.name or "名义值")
    _validate_series(real, real.name or "实际值")
    aligned = pd.concat(
        [nominal.rename("nominal"), real.rename("real")],
        axis=1,
        join="inner",
    ).sort_index()
    if aligned.empty:
        raise ValueError("名义值与实际值没有共同观测期")
    if (aligned.dropna() <= 0).any().any():
        raise ValueError("名义值和实际值必须为正")

    deflator = (aligned["nominal"] / aligned["real"] * 100).rename(
        "deflator"
    )
    nominal_growth = (
        100 * np.log(aligned["nominal"] / aligned["nominal"].shift(periods))
    ).rename("nominal_log_growth")
    real_growth = (
        100 * np.log(aligned["real"] / aligned["real"].shift(periods))
    ).rename("real_log_growth")
    deflator_growth = (
        100 * np.log(deflator / deflator.shift(periods))
    ).rename("deflator_log_growth")
    return NominalRealBridge(
        deflator=deflator,
        nominal_log_growth=nominal_growth,
        real_log_growth=real_growth,
        deflator_log_growth=deflator_growth,
        periods=periods,
    )


def calculate_diffusion(
    industries: pd.DataFrame,
    *,
    periods: int,
) -> pd.Series:
    """有效行业中实际增加值增长为正的行业占比。"""

    if periods <= 0:
        raise ValueError("比较期数必须为正整数")
    if industries.index.has_duplicates:
        raise ValueError("行业数据包含重复时期")
    growth = industries.pct_change(
        periods=periods,
        fill_method=None,
    )
    valid = growth.notna().sum(axis=1)
    positive = growth.gt(0).where(growth.notna()).sum(axis=1)
    return (positive / valid.replace(0, np.nan)).rename("diffusion")

