"""阿联酋增长诊断的纯计算函数。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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
class IndustryDiagnosticsResult:
    """行业增长广度、集中度与持续性诊断。"""

    contribution_result: ContributionResult
    breadth: pd.DataFrame
    concentration: pd.DataFrame
    persistence: pd.DataFrame


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


def _quarter_period_index(index: pd.Index) -> pd.PeriodIndex:
    if isinstance(index, pd.PeriodIndex):
        periods = index.asfreq("Q")
    else:
        try:
            periods = pd.DatetimeIndex(index).to_period("Q")
        except (TypeError, ValueError) as exc:
            raise ValueError("行业诊断要求季度时间索引") from exc
    expected = pd.period_range(periods.min(), periods.max(), freq="Q")
    if not periods.equals(expected):
        raise ValueError("季度索引必须连续")
    return periods


def _validate_industry_diagnostic_inputs(
    total: pd.Series,
    components: Mapping[str, pd.Series],
) -> None:
    _validate_series(total, total.name or "非油实际GDP")
    if not components:
        raise ValueError("至少需要一个行业")
    _quarter_period_index(total.index)
    for label, series in components.items():
        _validate_series(series, label)
        _quarter_period_index(series.index)
        if not series.index.equals(total.index):
            raise ValueError("行业与非油实际GDP的季度索引必须完全一致")
        if (series.dropna() <= 0).any():
            raise ValueError(f"行业{label}的不变价增加值必须为正")
    if (total.dropna() <= 0).any():
        raise ValueError("非油实际GDP必须为正")


def _breadth_pair(
    condition: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    label: str,
) -> tuple[pd.Series, pd.Series]:
    industry_count = condition.shape[1]
    condition_complete = condition.notna().all(axis=1)
    unweighted = (
        condition.astype(float)
        .mean(axis=1)
        .mul(100)
        .where(condition_complete)
        .rename(f"不加权｜{label}")
    )
    weighted_complete = condition_complete & weights.notna().all(axis=1)
    weighted = (
        weights.mul(condition.astype(float))
        .sum(axis=1, min_count=industry_count)
        .mul(100)
        .where(weighted_complete)
        .rename(f"加权｜{label}")
    )
    return unweighted, weighted


def _consecutive_positive_counts(growth: pd.DataFrame) -> pd.DataFrame:
    """每列统计连续正增长季度数；缺失值中断计数并保留缺失。"""

    result = pd.DataFrame(
        np.nan,
        index=growth.index,
        columns=growth.columns,
        dtype=float,
    )
    for column in growth.columns:
        series = growth[column]
        positive = series.gt(0)
        groups = (~positive).cumsum()
        counts = positive.groupby(groups).cumsum()
        result[column] = counts.where(positive, 0.0).mask(series.isna())
    return result


def calculate_industry_diagnostics(
    total: pd.Series,
    components: Mapping[str, pd.Series],
    *,
    periods: int = 4,
    history_min_periods: int = 8,
    persistence_window: int = 8,
    absolute_tolerance: float = 1e-5,
    relative_tolerance: float = 1e-10,
) -> IndustryDiagnosticsResult:
    """计算行业扩张广度、贡献集中度与增长持续性。"""

    if periods <= 0:
        raise ValueError("比较期数必须为正整数")
    if history_min_periods <= 0:
        raise ValueError("历史均值最小期数必须为正整数")
    if persistence_window <= 0:
        raise ValueError("持续性窗口必须为正整数")
    _validate_industry_diagnostic_inputs(total, components)
    aligned_total, levels = _align_components(total, components)
    industry_count = levels.shape[1]

    contribution_result = calculate_growth_contributions(
        aligned_total,
        {column: levels[column] for column in levels.columns},
        periods=periods,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    growth_rates = levels.div(levels.shift(periods)).sub(1).mul(100)
    base_year_shares = levels.shift(periods).div(
        aligned_total.shift(periods),
        axis=0,
    )
    current_shares = levels.div(aligned_total, axis=0)
    for shares in (base_year_shares, current_shares):
        complete = shares.notna().all(axis=1)
        share_error = (
            shares.sum(axis=1, min_count=industry_count).sub(1).abs()
        )
        if (share_error.loc[complete] > relative_tolerance).any():
            raise ValueError("行业权重之和未在容差内等于1")

    historical_mean = (
        growth_rates.shift(1)
        .expanding(min_periods=history_min_periods)
        .mean()
    )
    positive = growth_rates.gt(0).where(growth_rates.notna())
    above_history = growth_rates.gt(historical_mean).where(
        growth_rates.notna() & historical_mean.notna()
    )
    previous_growth = growth_rates.shift(1)
    accelerating = growth_rates.gt(previous_growth).where(
        growth_rates.notna() & previous_growth.notna()
    )
    positive_numeric = positive.astype(float)
    four_quarter_valid = (
        growth_rates.notna()
        .astype(int)
        .rolling(4, min_periods=4)
        .sum()
        .eq(4)
    )
    four_quarter_positive = (
        positive_numeric.rolling(4, min_periods=4)
        .sum()
        .eq(4)
        .where(four_quarter_valid)
    )
    breadth_series: list[pd.Series] = []
    for condition, label in (
        (positive, "正增长行业比例"),
        (above_history, "增速高于历史均值的行业比例"),
        (accelerating, "增速较上季度加快的行业比例"),
        (four_quarter_positive, "连续四季度正增长的行业比例"),
    ):
        unweighted, weighted = _breadth_pair(
            condition,
            base_year_shares,
            label=label,
        )
        breadth_series.extend((unweighted, weighted))
    breadth = pd.concat(breadth_series, axis=1)
    breadth = breadth[
        [
            *(column for column in breadth if column.startswith("不加权｜")),
            *(column for column in breadth if column.startswith("加权｜")),
        ]
    ]

    contributions = contribution_result.contributions
    complete_contributions = contributions.notna().all(axis=1)
    absolute_contribution_sum = contributions.abs().sum(
        axis=1,
        min_count=industry_count,
    ).rename("总变动强度")
    valid_concentration = complete_contributions & absolute_contribution_sum.gt(0)
    absolute_contribution_shares = contributions.abs().div(
        absolute_contribution_sum.replace(0, np.nan),
        axis=0,
    )
    absolute_hhi = (
        absolute_contribution_shares.pow(2)
        .sum(axis=1, min_count=industry_count)
        .where(valid_concentration)
        .rename("绝对贡献HHI")
    )
    equal_share_hhi = 1 / industry_count
    standardized_concentration = (
        absolute_hhi.sub(equal_share_hhi)
        .div(1 - equal_share_hhi)
        .mul(100)
        .clip(lower=0, upper=100)
        .rename("标准化绝对贡献集中度")
    )
    net_contribution = contributions.sum(
        axis=1,
        min_count=industry_count,
    ).where(complete_contributions)
    contribution_balance = (
        net_contribution.div(absolute_contribution_sum.replace(0, np.nan))
        .mul(100)
        .where(valid_concentration)
        .rename("贡献平衡指数")
    )

    def _driver_series(
        *,
        positive: bool,
    ) -> tuple[pd.Series, pd.Series]:
        masked = contributions.where(
            contributions.gt(0) if positive else contributions.lt(0)
        )
        valid = masked.notna().any(axis=1)
        best = masked.loc[valid]
        names = (
            best.idxmax(axis=1) if positive else best.idxmin(axis=1)
        ).reindex(contributions.index)
        values = (
            best.max(axis=1) if positive else best.min(axis=1)
        ).reindex(contributions.index)
        direction = "正向" if positive else "负向"
        return (
            names.rename(f"最大{direction}贡献行业"),
            values.rename(f"最大{direction}贡献"),
        )

    max_positive_industry, max_positive_contribution = _driver_series(
        positive=True
    )
    max_negative_industry, max_negative_contribution = _driver_series(
        positive=False
    )
    concentration = pd.concat(
        [
            contribution_balance,
            standardized_concentration,
            absolute_hhi,
            absolute_contribution_sum.where(valid_concentration),
            contribution_result.total_growth.where(valid_concentration).rename(
                "非油GDP同比"
            ),
            max_positive_industry.where(valid_concentration),
            max_positive_contribution.where(valid_concentration),
            max_negative_industry.where(valid_concentration),
            max_negative_contribution.where(valid_concentration),
        ],
        axis=1,
    )

    recent_four = growth_rates.rolling(4, min_periods=4).mean()
    recent_window = growth_rates.rolling(
        persistence_window,
        min_periods=persistence_window,
    ).mean()
    prior_four = (
        growth_rates.shift(1).rolling(4, min_periods=4).mean()
    )
    above_history_count = (
        above_history.astype(float)
        .rolling(
            persistence_window,
            min_periods=persistence_window,
        )
        .sum()
    )
    positive_streak = _consecutive_positive_counts(growth_rates)
    level_gap = growth_rates.sub(historical_mean)
    momentum_gap = growth_rates.sub(previous_growth)
    states = pd.DataFrame(
        pd.NA,
        index=growth_rates.index,
        columns=growth_rates.columns,
        dtype="object",
    )
    valid_state = level_gap.notna() & momentum_gap.notna()
    states = states.mask(
        valid_state & level_gap.gt(0) & momentum_gap.gt(0),
        "高位加速",
    )
    states = states.mask(
        valid_state & level_gap.gt(0) & momentum_gap.le(0),
        "高位放缓",
    )
    states = states.mask(
        valid_state & level_gap.le(0) & momentum_gap.gt(0),
        "低位改善",
    )
    states = states.mask(
        valid_state & level_gap.le(0) & momentum_gap.le(0),
        "低位恶化",
    )

    long_average_label = (
        f"最近{persistence_window}季度平均增速"
        if persistence_window != 4
        else "持续性窗口平均增速"
    )
    above_count_label = (
        f"最近{persistence_window}季度高于自身历史趋势次数"
    )
    quarter_labels = _quarter_period_index(growth_rates.index).astype(str)
    persistence_frames: list[pd.DataFrame] = []
    for position, quarter in enumerate(quarter_labels):
        persistence_frames.append(
            pd.DataFrame(
                {
                    "季度": quarter,
                    "行业": list(growth_rates.columns),
                    "当前实际增加值增速": growth_rates.iloc[
                        position
                    ].to_numpy(),
                    "最近4季度平均增速": recent_four.iloc[
                        position
                    ].to_numpy(),
                    long_average_label: recent_window.iloc[
                        position
                    ].to_numpy(),
                    "连续正增长季度数": positive_streak.iloc[
                        position
                    ].to_numpy(),
                    above_count_label: above_history_count.iloc[
                        position
                    ].to_numpy(),
                    "当季增速减过去4季度均值": (
                        growth_rates.iloc[position]
                        - prior_four.iloc[position]
                    ).to_numpy(),
                    "当季增速减历史趋势": level_gap.iloc[
                        position
                    ].to_numpy(),
                    "当季增速减上季度增速": momentum_gap.iloc[
                        position
                    ].to_numpy(),
                    "实际GDP占非油GDP比例": current_shares.iloc[
                        position
                    ].to_numpy(),
                    "行业状态": states.iloc[position].to_numpy(),
                }
            )
        )
    persistence = pd.concat(
        persistence_frames,
        ignore_index=True,
    ).set_index(["季度", "行业"])
    return IndustryDiagnosticsResult(
        contribution_result=contribution_result,
        breadth=breadth,
        concentration=concentration,
        persistence=persistence,
    )
