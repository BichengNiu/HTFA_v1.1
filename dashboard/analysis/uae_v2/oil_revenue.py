"""基于原油价格与产量估算阿联酋月度石油收入。"""

from __future__ import annotations

import pandas as pd


PRICE_PRIORITY = ("穆尔班现货", "迪拜现货", "布伦特现货")

PRICE_COLUMN = "月均油价"
PRICE_BENCHMARK_COLUMN = "价格基准"
PRODUCTION_COLUMN = "月均原油产量"
DAYS_COLUMN = "当月天数"
REVENUE_COLUMN = "月度石油收入"
MOM_COLUMN = "环比"
YOY_COLUMN = "同比"
YTD_COLUMN = "本年度累计收入"
PRICE_CONTRIBUTION_COLUMN = "价格拉动率"
PRODUCTION_CONTRIBUTION_COLUMN = "产量拉动率"


def estimate_monthly_oil_revenue(
    prices: pd.DataFrame,
    production: pd.Series,
) -> pd.DataFrame:
    """估算月度石油收入，金额单位为亿美元。

    每月价格依次采用穆尔班现货、迪拜现货和布伦特现货的月均值；
    价格或产量缺失的月份不生成收入，也不跨月填充。
    """

    missing_prices = [name for name in PRICE_PRIORITY if name not in prices.columns]
    if missing_prices:
        raise ValueError(f"缺少石油收入估算价格序列：{', '.join(missing_prices)}")

    clean_production = production.dropna().sort_index()
    if clean_production.empty:
        raise ValueError("原油产量没有有效观测，无法估算石油收入")

    price_periods = prices.index.to_period("M")
    monthly_prices = prices.loc[:, list(PRICE_PRIORITY)].groupby(price_periods).mean()
    production_periods = clean_production.index.to_period("M")
    monthly_production = clean_production.groupby(production_periods).mean()

    periods = pd.period_range(
        monthly_production.index.min(),
        monthly_production.index.max(),
        freq="M",
    )
    monthly_prices = monthly_prices.reindex(periods)
    monthly_production = monthly_production.reindex(periods)

    selected_price = pd.Series(index=periods, dtype="float64")
    selected_benchmark = pd.Series(index=periods, dtype="object")
    for benchmark in PRICE_PRIORITY:
        use_benchmark = selected_price.isna() & monthly_prices[benchmark].notna()
        if not use_benchmark.any():
            continue
        selected_price.loc[use_benchmark] = monthly_prices.loc[
            use_benchmark, benchmark
        ]
        selected_benchmark.loc[use_benchmark] = benchmark

    result = pd.DataFrame(index=periods)
    result[PRICE_COLUMN] = selected_price
    result[PRICE_BENCHMARK_COLUMN] = selected_benchmark
    result[PRODUCTION_COLUMN] = monthly_production
    result[DAYS_COLUMN] = periods.days_in_month.astype(int)
    result[REVENUE_COLUMN] = (
        result[PRICE_COLUMN]
        * result[PRODUCTION_COLUMN]
        * result[DAYS_COLUMN]
        / 100_000_000
    )
    result[MOM_COLUMN] = result[REVENUE_COLUMN].pct_change(
        fill_method=None
    ) * 100
    result[YOY_COLUMN] = result[REVENUE_COLUMN].pct_change(
        periods=12,
        fill_method=None,
    ) * 100
    prior_price = result[PRICE_COLUMN].shift(12)
    monthly_volume = result[PRODUCTION_COLUMN] * result[DAYS_COLUMN]
    prior_volume = monthly_volume.shift(12)
    prior_value = prior_price * prior_volume
    result[PRICE_CONTRIBUTION_COLUMN] = (
        (result[PRICE_COLUMN] - prior_price)
        * (monthly_volume + prior_volume)
        / 2
        / prior_value
        * 100
    )
    result[PRODUCTION_CONTRIBUTION_COLUMN] = (
        (monthly_volume - prior_volume)
        * (result[PRICE_COLUMN] + prior_price)
        / 2
        / prior_value
        * 100
    )
    result[YTD_COLUMN] = result[REVENUE_COLUMN].groupby(periods.year).cumsum()

    result = result.dropna(subset=[REVENUE_COLUMN]).copy()
    if result.empty:
        raise ValueError("油价与产量没有可对齐的有效月份，无法估算石油收入")
    result.index = result.index.to_timestamp(how="end").normalize()
    result.index.name = "月份"
    return result


__all__ = [
    "DAYS_COLUMN",
    "MOM_COLUMN",
    "PRICE_CONTRIBUTION_COLUMN",
    "PRICE_BENCHMARK_COLUMN",
    "PRICE_COLUMN",
    "PRICE_PRIORITY",
    "PRODUCTION_COLUMN",
    "PRODUCTION_CONTRIBUTION_COLUMN",
    "REVENUE_COLUMN",
    "YOY_COLUMN",
    "YTD_COLUMN",
    "estimate_monthly_oil_revenue",
]
