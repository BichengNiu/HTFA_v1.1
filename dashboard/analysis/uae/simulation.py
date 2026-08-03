"""缺失宏观指标的确定性、运行时模拟数据。

模拟数据只服务于界面和诊断流程开发，不写回工作簿，不作为事实或预测。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import numpy as np
import pandas as pd

from dashboard.analysis.uae.contracts import (
    DataProvenance,
    ProvenanceKind,
    UAEDataBundle,
)

SIMULATED_SOURCE = "模拟数据（非官方，仅用于界面开发）"


def _seed(group_id: str) -> int:
    digest = hashlib.sha256(
        f"HTFA-UAE-RUNTIME-2026::{group_id}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _rng(group_id: str) -> np.random.Generator:
    return np.random.default_rng(_seed(group_id))


def _as_series(values, index, name) -> pd.Series:
    return pd.Series(
        np.asarray(values, dtype=float),
        index=index,
        name=name,
    )


def _monthly_index(real_bundle: UAEDataBundle) -> pd.DatetimeIndex:
    end = pd.Timestamp("2025-12-31")
    candidates = [
        series.index.max()
        for indicator_id, series in real_bundle.series_by_id.items()
        if real_bundle.provenance_by_id[indicator_id].frequency == "monthly"
        and len(series.index)
    ]
    if candidates:
        end = max(end, pd.Timestamp(max(candidates)))
    return pd.date_range("2012-01-31", end=end, freq="ME")


def _annual_index(quarterly_index: pd.Index) -> pd.DatetimeIndex:
    start_year = max(2012, pd.Timestamp(quarterly_index.min()).year)
    end_year = pd.Timestamp(quarterly_index.max()).year
    return pd.date_range(
        f"{start_year}-12-31",
        f"{end_year}-12-31",
        freq="YE",
    )


def _smooth_growth_index(
    index: pd.Index,
    *,
    base: float,
    monthly_growth: float,
    volatility: float,
    group_id: str,
) -> pd.Series:
    rng = _rng(group_id)
    innovations = rng.normal(monthly_growth, volatility, len(index))
    return _as_series(
        base * np.exp(np.cumsum(innovations)),
        index,
        group_id,
    )


class _SimulationBuilder:
    def __init__(self, real_bundle: UAEDataBundle):
        self.real_bundle = real_bundle
        self.series = dict(real_bundle.series_by_id)
        self.provenance = dict(real_bundle.provenance_by_id)

    def add(
        self,
        indicator_id: str,
        values,
        index: pd.Index,
        *,
        display_name: str,
        frequency: str,
        unit: str,
        coverage: str = "阿联酋全国",
        note: str = "",
    ) -> None:
        """仅在真实数据缺失时加入模拟序列。"""

        if indicator_id in self.series:
            return
        series = _as_series(values, index, display_name)
        self.series[indicator_id] = series
        self.provenance[indicator_id] = DataProvenance(
            indicator_id=indicator_id,
            display_name=display_name,
            kind=ProvenanceKind.SIMULATED,
            source=SIMULATED_SOURCE,
            frequency=frequency,
            unit=unit,
            coverage=coverage,
            as_of=str(index.max()),
            note=note or "固定种子生成；不代表官方统计或预测。",
        )

    def result(self) -> UAEDataBundle:
        return UAEDataBundle(
            series_by_id=self.series,
            provenance_by_id=self.provenance,
        )


def _add_nominal_gdp_anchor(builder: _SimulationBuilder) -> None:
    """缺失名义GDP时，生成仅供其他模拟账户定标的序列。"""

    real = builder.real_bundle.require_series("growth.real_gdp").dropna()
    t = np.arange(len(real), dtype=float)
    deflator = 0.80 * np.exp(0.008 * t)
    builder.add(
        "growth.nominal_gdp",
        real * deflator,
        real.index,
        display_name="名义GDP（模拟定标）",
        frequency="quarterly",
        unit=builder.real_bundle.require_provenance("growth.real_gdp").unit,
        note=(
            "由真实实际GDP和固定确定性平减指数路径生成；"
            "只用于模拟账户定标，不作为名义GDP分析。"
        ),
    )


def _add_growth_accounts(builder: _SimulationBuilder) -> None:
    nominal = builder.series["growth.nominal_gdp"].dropna()
    index = nominal.index
    t = np.arange(len(index), dtype=float)

    household = nominal * (0.31 + 0.01 * np.sin(t / 5.0))
    government = nominal * (0.12 + 0.004 * np.cos(t / 6.0))
    investment = nominal * (0.27 + 0.008 * np.sin(t / 7.0 + 0.8))
    inventories = nominal * (0.01 + 0.003 * np.sin(t / 3.0))
    exports = nominal * (0.91 + 0.025 * np.sin(t / 4.5))
    imports = household + government + investment + inventories + exports - nominal

    expenditure = {
        "expenditure.household_consumption": ("居民最终消费支出", household),
        "expenditure.government_consumption": ("政府最终消费支出", government),
        "expenditure.gfcf": ("固定资本形成总额", investment),
        "expenditure.inventory_change": ("存货变化", inventories),
        "expenditure.exports": ("货物和服务出口", exports),
        "expenditure.imports": ("货物和服务进口", imports),
    }
    for indicator_id, (name, values) in expenditure.items():
        builder.add(
            indicator_id,
            values,
            index,
            display_name=name,
            frequency="quarterly",
            unit=builder.provenance["growth.nominal_gdp"].unit,
            note="按支出法恒等式约束生成。",
        )

    compensation = nominal * (0.28 + 0.006 * np.sin(t / 6.0))
    mixed_income = nominal * (0.04 + 0.002 * np.cos(t / 5.0))
    taxes_net = nominal * (0.065 + 0.003 * np.sin(t / 4.0))
    operating_surplus = nominal - compensation - mixed_income - taxes_net
    income = {
        "income.compensation": ("劳动者报酬", compensation),
        "income.operating_surplus": ("营业盈余", operating_surplus),
        "income.mixed_income": ("混合收入", mixed_income),
        "income.production_taxes_net": ("生产税净额", taxes_net),
    }
    for indicator_id, (name, values) in income.items():
        builder.add(
            indicator_id,
            values,
            index,
            display_name=name,
            frequency="quarterly",
            unit=builder.provenance["growth.nominal_gdp"].unit,
            note="按收入法恒等式约束生成。",
        )


def _add_inflation(builder: _SimulationBuilder, monthly: pd.DatetimeIndex) -> None:
    food = _smooth_growth_index(
        monthly,
        base=100,
        monthly_growth=0.0022,
        volatility=0.0025,
        group_id="inflation.food",
    )
    housing = _smooth_growth_index(
        monthly,
        base=100,
        monthly_growth=0.0028,
        volatility=0.0012,
        group_id="inflation.housing",
    )
    transport = _smooth_growth_index(
        monthly,
        base=100,
        monthly_growth=0.0018,
        volatility=0.0040,
        group_id="inflation.transport",
    )
    other = _smooth_growth_index(
        monthly,
        base=100,
        monthly_growth=0.0017,
        volatility=0.0010,
        group_id="inflation.other",
    )
    all_items = 0.14 * food + 0.35 * housing + 0.12 * transport + 0.39 * other
    series = {
        "inflation.cpi_all": ("CPI总指数", all_items),
        "inflation.cpi_food": ("食品CPI", food),
        "inflation.cpi_housing": ("住房CPI", housing),
        "inflation.cpi_transport": ("交通CPI", transport),
        "inflation.cpi_other": ("其他商品和服务CPI", other),
    }
    for indicator_id, (name, values) in series.items():
        builder.add(
            indicator_id,
            values,
            monthly,
            display_name=name,
            frequency="monthly",
            unit="指数，2012年=100",
            note="分类指数按固定权重加总为总体CPI。",
        )


def _add_labor(
    builder: _SimulationBuilder,
    monthly: pd.DatetimeIndex,
    annual: pd.DatetimeIndex,
) -> None:
    years = np.arange(len(annual), dtype=float)
    population = 8.9e6 * np.power(1.025, years)
    labor_force = population * (0.69 + 0.004 * np.sin(years / 2.0))
    unemployment_rate = 2.8 - 0.4 * np.sin(years / 3.0)
    employed = labor_force * (1 - unemployment_rate / 100)
    annual_series = {
        "labor.population": ("总人口", population, "人"),
        "labor.labor_force": ("劳动力人口", labor_force, "人"),
        "labor.employed": ("就业人口", employed, "人"),
        "labor.unemployment_rate": (
            "失业率",
            unemployment_rate,
            "%",
        ),
    }
    for indicator_id, (name, values, unit) in annual_series.items():
        builder.add(
            indicator_id,
            values,
            annual,
            display_name=name,
            frequency="yearly",
            unit=unit,
        )

    m = np.arange(len(monthly), dtype=float)
    wps_employees = 3.8e6 * np.power(1.006, m)
    average_wage = 7600 * np.power(1.0017, m) * (
        1 + 0.01 * np.sin(m / 12.0)
    )
    builder.add(
        "labor.wps_employees",
        wps_employees,
        monthly,
        display_name="WPS覆盖雇员人数",
        frequency="monthly",
        unit="人",
        coverage="WPS覆盖私营部门雇员",
    )
    builder.add(
        "labor.wps_average_wage",
        average_wage,
        monthly,
        display_name="WPS平均工资",
        frequency="monthly",
        unit="迪拉姆/月",
        coverage="WPS覆盖私营部门雇员",
    )


def _add_fiscal_external(builder: _SimulationBuilder) -> None:
    nominal = builder.series["growth.nominal_gdp"].dropna()
    index = nominal.index
    t = np.arange(len(index), dtype=float)

    revenue = nominal * (0.31 + 0.025 * np.sin(t / 4.0))
    expense = nominal * (0.22 + 0.008 * np.cos(t / 5.0))
    nonfinancial_assets = nominal * (0.045 + 0.004 * np.sin(t / 6.0))
    net_lending = revenue - expense - nonfinancial_assets
    fiscal = {
        "fiscal.total_revenue": ("一般政府总收入", revenue),
        "fiscal.total_expense": ("一般政府经常支出", expense),
        "fiscal.net_nonfinancial_assets": (
            "非金融资产净购置",
            nonfinancial_assets,
        ),
        "fiscal.net_lending_borrowing": (
            "一般政府净借贷/净借款",
            net_lending,
        ),
    }
    unit = builder.provenance["growth.nominal_gdp"].unit
    for indicator_id, (name, values) in fiscal.items():
        builder.add(
            indicator_id,
            values,
            index,
            display_name=name,
            frequency="quarterly",
            unit=unit,
            coverage="合并一般政府",
            note="按政府财政统计恒等式约束生成。",
        )

    goods = nominal * (0.205 + 0.02 * np.sin(t / 4.0))
    services = nominal * (0.025 + 0.004 * np.cos(t / 6.0))
    primary = nominal * (-0.025 + 0.003 * np.sin(t / 7.0))
    secondary = nominal * (-0.055 - 0.003 * np.cos(t / 5.0))
    current_account = goods + services + primary + secondary
    external = {
        "external.goods_balance": ("货物贸易余额", goods),
        "external.services_balance": ("服务贸易余额", services),
        "external.primary_income": ("初次收入余额", primary),
        "external.secondary_income": ("二次收入余额", secondary),
        "external.current_account": ("经常账户余额", current_account),
    }
    for indicator_id, (name, values) in external.items():
        builder.add(
            indicator_id,
            values,
            index,
            display_name=name,
            frequency="quarterly",
            unit=unit,
            note="按国际收支经常账户恒等式约束生成。",
        )


def _add_monetary_high_frequency(
    builder: _SimulationBuilder,
    monthly: pd.DatetimeIndex,
) -> None:
    m = np.arange(len(monthly), dtype=float)
    rate_cycle = 1.5 + 1.8 * (1 + np.sin((m - 90) / 18.0)) / 2
    fed = rate_cycle
    base_rate = fed + 0.15
    eibor = base_rate + 0.35 + 0.10 * np.sin(m / 5.0)

    m1 = 500e9 * np.power(1.006, m)
    m2 = m1 * (1.75 + 0.03 * np.sin(m / 12.0))
    m3 = m2 * (1.12 + 0.01 * np.cos(m / 10.0))
    deposits = m3 * 1.05
    credit = deposits * (0.83 + 0.015 * np.sin(m / 9.0))

    series = {
        "monetary.fed_iorb": ("美联储政策利率", fed, "%"),
        "monetary.cbuae_base_rate": ("CBUAE基础利率", base_rate, "%"),
        "monetary.eibor_3m": ("3个月EIBOR", eibor, "%"),
        "monetary.m1": ("M1", m1, "迪拉姆"),
        "monetary.m2": ("M2", m2, "迪拉姆"),
        "monetary.m3": ("M3", m3, "迪拉姆"),
        "banking.total_deposits": ("银行存款", deposits, "迪拉姆"),
        "banking.total_credit": ("银行信贷", credit, "迪拉姆"),
        "banking.private_credit": (
            "私营部门信贷",
            credit * 0.68,
            "迪拉姆",
        ),
        "banking.retail_credit": (
            "居民零售信贷",
            credit * 0.22,
            "迪拉姆",
        ),
    }
    for indicator_id, (name, values, unit) in series.items():
        builder.add(
            indicator_id,
            values,
            monthly,
            display_name=name,
            frequency="monthly",
            unit=unit,
        )

    rng = _rng("high_frequency")
    dubai_crude = 72 + 12 * np.sin(m / 11.0) + rng.normal(0, 2.0, len(m))
    pmi = 53 + 1.5 * np.sin(m / 8.0) + rng.normal(0, 0.5, len(m))
    payments = 100e9 * np.power(1.008, m) * (1 + 0.03 * np.sin(m / 6.0))
    visitors = 1.1e6 * np.power(1.004, m) * (
        1 + 0.18 * np.sin(2 * np.pi * m / 12)
    )
    property_index = 100 * np.power(1.003, m) * (
        1 + 0.025 * np.sin(m / 10.0)
    )
    high_frequency = {
        "oil.dubai_crude_price": (
            "迪拜原油价格",
            dubai_crude,
            "美元/桶",
            "全球",
        ),
        "business.pmi_headline": (
            "非油私营部门PMI",
            pmi,
            "指数",
            "非油私营部门样本",
        ),
        "payments.card_value": (
            "银行卡支付金额",
            payments,
            "迪拉姆",
            "支付系统覆盖",
        ),
        "tourism.dubai_visitors": (
            "迪拜国际游客",
            visitors,
            "人次",
            "迪拜",
        ),
        "property.dubai_rppi": (
            "迪拜住宅价格指数",
            property_index,
            "指数",
            "迪拜",
        ),
    }
    for indicator_id, (name, values, unit, coverage) in high_frequency.items():
        builder.add(
            indicator_id,
            values,
            monthly,
            display_name=name,
            frequency="monthly",
            unit=unit,
            coverage=coverage,
        )

    daily = pd.date_range(
        monthly.min().normalize(),
        monthly.max().normalize(),
        freq="B",
    )
    dfm = _smooth_growth_index(
        daily,
        base=1600,
        monthly_growth=0.00018,
        volatility=0.008,
        group_id="market.dfm_index",
    )
    builder.add(
        "market.dfm_index",
        dfm,
        daily,
        display_name="DFM综合股票指数",
        frequency="daily",
        unit="指数",
        coverage="迪拜金融市场",
    )


def merge_runtime_simulation(real_bundle: UAEDataBundle) -> UAEDataBundle:
    """将模拟序列加入真实数据集，绝不覆盖真实指标。"""

    builder = _SimulationBuilder(real_bundle)
    quarterly = real_bundle.require_series("growth.real_gdp").dropna().index
    monthly = _monthly_index(real_bundle)
    annual = _annual_index(quarterly)

    generators: tuple[Callable[[], None], ...] = (
        lambda: _add_nominal_gdp_anchor(builder),
        lambda: _add_growth_accounts(builder),
        lambda: _add_inflation(builder, monthly),
        lambda: _add_labor(builder, monthly, annual),
        lambda: _add_fiscal_external(builder),
        lambda: _add_monetary_high_frequency(builder, monthly),
    )
    for generate in generators:
        generate()
    return builder.result()
