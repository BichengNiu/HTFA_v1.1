"""阿联酋五个详细宏观页面的分析服务。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from dashboard.analysis.uae.contracts import (
    DataProvenance,
    EvidenceClass,
    EvidenceItem,
    ProvenanceKind,
    UAEDataBundle,
)
from dashboard.analysis.uae.data_adapter import (
    DEFAULT_UAE_WORKBOOK,
    load_runtime_uae_bundle,
)
from dashboard.analysis.uae.diagnostics import build_diagnostic
from dashboard.analysis.uae.growth import (
    calculate_diffusion,
    calculate_growth_contributions,
    calculate_nominal_real_bridge,
)
from dashboard.analysis.uae.indicator_catalog import (
    INDUSTRY_NAMES,
    REAL_INDUSTRY_IDS,
)
from dashboard.analysis.uae.results import (
    MacroPanelResult,
    MetricSnapshot,
    MonitoringDashboardResult,
)


def _period_label(value: Any) -> str:
    if isinstance(value, pd.Period):
        return str(value)
    timestamp = pd.Timestamp(value)
    if timestamp.is_quarter_end or timestamp.month in {1, 4, 7, 10}:
        return f"{timestamp.year}Q{timestamp.quarter}"
    return timestamp.strftime("%Y-%m")


def _latest(series: pd.Series) -> tuple[Any, float]:
    clean = series.dropna()
    if clean.empty:
        raise ValueError(f"指标{series.name or ''}没有有效观测")
    return clean.index[-1], float(clean.iloc[-1])


def _growth(series: pd.Series, periods: int) -> pd.Series:
    return (series / series.shift(periods) - 1) * 100


def _derived_kind(
    bundle: UAEDataBundle,
    indicator_ids: Iterable[str],
) -> ProvenanceKind:
    return (
        ProvenanceKind.SIMULATED
        if any(bundle.is_simulated(indicator_id) for indicator_id in indicator_ids)
        else ProvenanceKind.REAL
    )


def _metric(
    *,
    label: str,
    series: pd.Series,
    unit: str,
    kind: ProvenanceKind,
    help_text: str = "",
) -> MetricSnapshot:
    period, value = _latest(series)
    return MetricSnapshot(
        label=label,
        value=value,
        unit=unit,
        period=_period_label(period),
        provenance_kind=kind,
        help_text=help_text,
    )


def _evidence(
    *,
    bundle: UAEDataBundle,
    indicator_id: str,
    label: str,
    value: float,
    unit: str,
    evidence_class: EvidenceClass,
    as_of: str | None = None,
    note: str = "",
) -> EvidenceItem:
    provenance = bundle.require_provenance(indicator_id)
    return EvidenceItem(
        label=label,
        value=value,
        unit=unit,
        evidence_class=evidence_class,
        provenance_kind=provenance.kind,
        as_of=as_of or provenance.as_of,
        note=note,
    )


def _provenance_subset(
    bundle: UAEDataBundle,
    indicator_ids: Iterable[str],
) -> dict[str, DataProvenance]:
    return {
        indicator_id: bundle.require_provenance(indicator_id)
        for indicator_id in indicator_ids
    }


def build_growth_panel(bundle: UAEDataBundle) -> MacroPanelResult:
    """生产法增长、行业贡献和名义实际桥接。"""

    real_gdp = bundle.require_series("growth.real_gdp").dropna()
    nominal_gdp = bundle.require_series("growth.nominal_gdp").dropna()
    nonoil = bundle.require_series("growth.nonoil_real_gdp").dropna()
    oil = (real_gdp - nonoil).rename("石油")

    oil_nonoil = calculate_growth_contributions(
        real_gdp,
        {"石油": oil, "非油": nonoil},
        periods=4,
    )

    industry_series = {
        INDUSTRY_NAMES[industry_id][1]: bundle.require_series(
            f"industry.{industry_id}.real"
        ).dropna()
        for industry_id in INDUSTRY_NAMES
    }
    industry_frame = pd.concat(industry_series, axis=1)
    common = industry_frame.index.intersection(real_gdp.index)
    residual = (
        real_gdp.loc[common] - industry_frame.loc[common].sum(axis=1)
    ).rename("其他行业、税收与残差")
    industry_components = dict(industry_series)
    industry_components["其他行业、税收与残差"] = residual
    industry_contributions = calculate_growth_contributions(
        real_gdp,
        industry_components,
        periods=4,
    )

    bridge = calculate_nominal_real_bridge(
        nominal_gdp,
        real_gdp,
        periods=4,
    )
    diffusion = calculate_diffusion(industry_frame, periods=4)
    total_growth = oil_nonoil.total_growth
    nonoil_growth = _growth(nonoil, 4).rename("非油GDP同比")
    oil_growth = _growth(oil, 4).rename("石油GDP同比")

    latest_contributions = (
        industry_contributions.contributions.dropna(how="all").iloc[-1]
    )
    top_name = latest_contributions.idxmax()
    top_value = float(latest_contributions.max())
    total_period, total_value = _latest(total_growth)
    nonoil_period, nonoil_value = _latest(nonoil_growth)
    brent_growth = _growth(
        bundle.require_series("oil.brent_price"),
        12,
    ).rename("Brent同比")
    _, brent_value = _latest(brent_growth)

    evidence = (
        _evidence(
            bundle=bundle,
            indicator_id="growth.real_gdp",
            label="实际GDP同比",
            value=total_value,
            unit="%",
            evidence_class=EvidenceClass.ACCOUNTING,
            as_of=_period_label(total_period),
        ),
        _evidence(
            bundle=bundle,
            indicator_id="growth.nonoil_real_gdp",
            label="非油GDP同比",
            value=nonoil_value,
            unit="%",
            evidence_class=EvidenceClass.ACCOUNTING,
            as_of=_period_label(nonoil_period),
        ),
        _evidence(
            bundle=bundle,
            indicator_id="oil.brent_price",
            label="Brent价格同比",
            value=brent_value,
            unit="%",
            evidence_class=EvidenceClass.MECHANISM,
        ),
    )
    direction = "扩张" if total_value >= 0 else "收缩"
    headline = build_diagnostic(
        title="经济增长与结构",
        result_sentence=(
            f"实际GDP在{_period_label(total_period)}同比"
            f"{direction}{abs(total_value):.1f}%。"
        ),
        accounting_sentence=(
            f"行业核算中，{top_name}贡献最大，为{top_value:.1f}个百分点；"
            "未覆盖活动、税收和统计差异单列为残差。"
        ),
        mechanism_sentence=(
            f"Brent价格同比为{brent_value:.1f}%，"
            "该价格端信号与石油渠道的判断一并展示。"
        ),
        evidence=evidence,
        limitation=(
            "Brent价格为运行时模拟序列，因此只能演示机制链，"
            "不能作为当前经济事实。"
        ),
        accounting_complete=True,
    )

    trend = pd.concat(
        [
            total_growth.rename("实际GDP同比"),
            nonoil_growth,
            oil_growth,
        ],
        axis=1,
    )
    mechanism = pd.concat(
        [
            _growth(
                bundle.require_series("oil.crude_production"),
                12,
            ).rename("原油产量同比"),
            brent_growth,
        ],
        axis=1,
    )
    nominal_real = pd.concat(
        [
            bridge.nominal_log_growth.rename("名义增长"),
            bridge.real_log_growth.rename("实际增长"),
            bridge.deflator_log_growth.rename("平减指数变化"),
        ],
        axis=1,
    )
    source_ids = (
        "growth.real_gdp",
        "growth.nominal_gdp",
        "growth.nonoil_real_gdp",
        "oil.crude_production",
        "oil.brent_price",
        *REAL_INDUSTRY_IDS,
    )
    return MacroPanelResult(
        key="growth",
        title="经济增长与结构",
        headline=headline,
        metrics=(
            _metric(
                label="实际GDP同比",
                series=total_growth,
                unit="%",
                kind=ProvenanceKind.REAL,
            ),
            _metric(
                label="非油GDP同比",
                series=nonoil_growth,
                unit="%",
                kind=ProvenanceKind.REAL,
            ),
            _metric(
                label="行业扩散度",
                series=diffusion * 100,
                unit="%",
                kind=ProvenanceKind.REAL,
                help_text="实际增加值同比为正的有效行业占比",
            ),
            _metric(
                label="GDP平减指数变化",
                series=bridge.deflator_log_growth,
                unit="对数百分点",
                kind=ProvenanceKind.REAL,
            ),
        ),
        series_groups={
            "增长趋势": trend,
            "石油机制证据": mechanism,
            "名义—实际桥接": nominal_real,
        },
        decomposition_tables={
            "油与非油贡献": oil_nonoil.contributions,
            "行业增长贡献": industry_contributions.contributions,
        },
        provenance=_provenance_subset(bundle, source_ids),
        methodology_notes=(
            "增长贡献使用同价增加值水平计算，单位为百分点。",
            "行业未覆盖部分不分摊，单列为“其他行业、税收与残差”。",
            "名义—实际桥接采用对数差分，三部分精确可加。",
        ),
    )


def build_inflation_panel(bundle: UAEDataBundle) -> MacroPanelResult:
    """CPI分类贡献及国内、外部机制信号。"""

    category_ids = (
        "inflation.cpi_food",
        "inflation.cpi_housing",
        "inflation.cpi_transport",
        "inflation.cpi_other",
    )
    names = ("食品", "住房", "交通", "其他")
    weights = np.array([0.14, 0.35, 0.12, 0.39])
    overall = bundle.require_series("inflation.cpi_all")
    overall_yoy = _growth(overall, 12).rename("总体CPI同比")
    category_yoy = pd.concat(
        [
            _growth(bundle.require_series(indicator_id), 12).rename(name)
            for indicator_id, name in zip(category_ids, names)
        ],
        axis=1,
    )
    contributions = category_yoy.mul(weights, axis=1)
    housing_yoy = category_yoy["住房"]
    food_yoy = category_yoy["食品"]
    three_month = (
        (overall / overall.shift(3)).pow(4) - 1
    ) * 100
    wage_yoy = _growth(
        bundle.require_series("labor.wps_average_wage"),
        12,
    ).rename("WPS平均工资同比")
    brent_yoy = _growth(
        bundle.require_series("oil.brent_price"),
        12,
    ).rename("Brent同比")
    mechanism = pd.concat([housing_yoy, wage_yoy, brent_yoy], axis=1)

    period, overall_value = _latest(overall_yoy)
    latest_contribution = contributions.dropna(how="all").iloc[-1]
    top_name = latest_contribution.abs().idxmax()
    top_value = float(latest_contribution[top_name])
    _, wage_value = _latest(wage_yoy)
    evidence = (
        _evidence(
            bundle=bundle,
            indicator_id="inflation.cpi_all",
            label="总体CPI同比",
            value=overall_value,
            unit="%",
            evidence_class=EvidenceClass.ACCOUNTING,
        ),
        _evidence(
            bundle=bundle,
            indicator_id="labor.wps_average_wage",
            label="WPS平均工资同比",
            value=wage_value,
            unit="%",
            evidence_class=EvidenceClass.MECHANISM,
        ),
    )
    headline = build_diagnostic(
        title="通货膨胀",
        result_sentence=(
            f"总体CPI在{_period_label(period)}同比变化"
            f"{overall_value:.1f}%。"
        ),
        accounting_sentence=(
            f"{top_name}分类的绝对贡献最大，为{top_value:.1f}个百分点。"
        ),
        mechanism_sentence=(
            f"WPS平均工资同比为{wage_value:.1f}%，"
            "与成本端压力的判断共同展示。"
        ),
        evidence=evidence,
        limitation="本页CPI及机制变量均为模拟数据，只用于检验页面逻辑。",
        accounting_complete=True,
    )
    source_ids = (
        "inflation.cpi_all",
        *category_ids,
        "labor.wps_average_wage",
        "oil.brent_price",
    )
    return MacroPanelResult(
        key="inflation",
        title="通货膨胀",
        headline=headline,
        metrics=(
            _metric(
                label="总体CPI同比",
                series=overall_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="三个月年化动量",
                series=three_month,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="住房CPI同比",
                series=housing_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="食品CPI同比",
                series=food_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
        ),
        series_groups={
            "通胀趋势": pd.concat(
                [overall_yoy, category_yoy],
                axis=1,
            ),
            "通胀机制证据": mechanism,
        },
        decomposition_tables={"CPI分类贡献": contributions},
        provenance=_provenance_subset(bundle, source_ids),
        methodology_notes=(
            "总体CPI由四个模拟分类指数按固定权重加总。",
            "核心通胀未作为官方指标展示。",
            "工资、油价等变量只作为机制证据，不作为因果识别。",
        ),
    )


def build_labor_panel(bundle: UAEDataBundle) -> MacroPanelResult:
    """就业、工资、实际购买力和劳动收入。"""

    employees = bundle.require_series("labor.wps_employees")
    wage = bundle.require_series("labor.wps_average_wage")
    cpi = bundle.require_series("inflation.cpi_all")
    employment_yoy = _growth(employees, 12).rename("WPS就业同比")
    wage_yoy = _growth(wage, 12).rename("名义工资同比")
    real_wage_index = (wage / cpi * 100).rename("实际工资指数")
    real_wage_yoy = _growth(real_wage_index, 12).rename("实际工资同比")
    real_payroll = (employees * wage / cpi * 100).rename("实际工资总额指数")
    real_payroll_yoy = _growth(real_payroll, 12).rename("实际工资总额同比")
    unemployment = bundle.require_series("labor.unemployment_rate")

    period, employment_value = _latest(employment_yoy)
    _, real_wage_value = _latest(real_wage_yoy)
    evidence = (
        _evidence(
            bundle=bundle,
            indicator_id="labor.wps_employees",
            label="WPS就业同比",
            value=employment_value,
            unit="%",
            evidence_class=EvidenceClass.ACCOUNTING,
        ),
        _evidence(
            bundle=bundle,
            indicator_id="labor.wps_average_wage",
            label="实际工资同比",
            value=real_wage_value,
            unit="%",
            evidence_class=EvidenceClass.MECHANISM,
        ),
    )
    headline = build_diagnostic(
        title="就业与居民收入",
        result_sentence=(
            f"WPS覆盖就业在{_period_label(period)}同比变化"
            f"{employment_value:.1f}%。"
        ),
        accounting_sentence=(
            f"经CPI调整后的平均工资同比变化{real_wage_value:.1f}%。"
        ),
        mechanism_sentence=(
            "就业数量和实际工资共同用于判断私营部门劳动收入动能。"
        ),
        evidence=evidence,
        limitation=(
            "全部序列均为模拟数据，且WPS口径不代表全国全部就业和居民收入。"
        ),
        accounting_complete=True,
    )
    source_ids = (
        "labor.population",
        "labor.labor_force",
        "labor.employed",
        "labor.unemployment_rate",
        "labor.wps_employees",
        "labor.wps_average_wage",
        "inflation.cpi_all",
    )
    annual_structure = pd.concat(
        [
            bundle.require_series("labor.population").rename("人口"),
            bundle.require_series("labor.labor_force").rename("劳动力"),
            bundle.require_series("labor.employed").rename("就业"),
        ],
        axis=1,
    )
    return MacroPanelResult(
        key="labor",
        title="就业与居民收入",
        headline=headline,
        metrics=(
            _metric(
                label="WPS就业同比",
                series=employment_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="名义工资同比",
                series=wage_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="实际工资同比",
                series=real_wage_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="失业率",
                series=unemployment,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
        ),
        series_groups={
            "就业与工资动能": pd.concat(
                [
                    employment_yoy,
                    wage_yoy,
                    real_wage_yoy,
                    real_payroll_yoy,
                ],
                axis=1,
            ),
            "人口—劳动力—就业": annual_structure,
        },
        decomposition_tables={},
        provenance=_provenance_subset(bundle, source_ids),
        methodology_notes=(
            "劳动收入近似为WPS覆盖雇员人数乘以平均工资。",
            "实际工资和实际工资总额使用模拟CPI调整。",
            "WPS只代表覆盖样本，不能外推为全国全部居民收入。",
        ),
    )


def build_fiscal_external_panel(bundle: UAEDataBundle) -> MacroPanelResult:
    """一般政府财政与国际收支。"""

    nominal = bundle.require_series("growth.nominal_gdp")
    revenue = bundle.require_series("fiscal.total_revenue")
    expense = bundle.require_series("fiscal.total_expense")
    capital = bundle.require_series("fiscal.net_nonfinancial_assets")
    fiscal_balance = bundle.require_series("fiscal.net_lending_borrowing")
    current_account = bundle.require_series("external.current_account")
    fiscal_ratio = (fiscal_balance / nominal * 100).rename("财政余额/GDP")
    current_ratio = (current_account / nominal * 100).rename("经常账户/GDP")

    fiscal_components = pd.concat(
        [
            revenue.rename("收入"),
            (-expense).rename("经常支出"),
            (-capital).rename("非金融资产净购置"),
        ],
        axis=1,
    )
    external_components = pd.concat(
        [
            bundle.require_series("external.goods_balance").rename("货物"),
            bundle.require_series("external.services_balance").rename("服务"),
            bundle.require_series("external.primary_income").rename("初次收入"),
            bundle.require_series("external.secondary_income").rename("二次收入"),
        ],
        axis=1,
    )
    period, fiscal_value = _latest(fiscal_ratio)
    _, current_value = _latest(current_ratio)
    evidence = (
        _evidence(
            bundle=bundle,
            indicator_id="fiscal.net_lending_borrowing",
            label="一般政府财政余额/GDP",
            value=fiscal_value,
            unit="%",
            evidence_class=EvidenceClass.ACCOUNTING,
        ),
        _evidence(
            bundle=bundle,
            indicator_id="external.current_account",
            label="经常账户/GDP",
            value=current_value,
            unit="%",
            evidence_class=EvidenceClass.ACCOUNTING,
        ),
    )
    headline = build_diagnostic(
        title="财政与外部平衡",
        result_sentence=(
            f"{_period_label(period)}一般政府财政余额相当于GDP的"
            f"{fiscal_value:.1f}%。"
        ),
        accounting_sentence=(
            f"经常账户余额相当于GDP的{current_value:.1f}%，"
            "货物、服务、初次收入和二次收入分别列示。"
        ),
        mechanism_sentence=(
            "财政缓冲和外部盈余共同用于观察油价及资本流动冲击的承受能力。"
        ),
        evidence=evidence,
        limitation="财政和国际收支序列均为模拟数据，不代表官方余额。",
        accounting_complete=True,
    )
    source_ids = (
        "growth.nominal_gdp",
        "fiscal.total_revenue",
        "fiscal.total_expense",
        "fiscal.net_nonfinancial_assets",
        "fiscal.net_lending_borrowing",
        "external.goods_balance",
        "external.services_balance",
        "external.primary_income",
        "external.secondary_income",
        "external.current_account",
    )
    return MacroPanelResult(
        key="fiscal_external",
        title="财政与外部平衡",
        headline=headline,
        metrics=(
            _metric(
                label="财政余额/GDP",
                series=fiscal_ratio,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="经常账户/GDP",
                series=current_ratio,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="政府收入/GDP",
                series=revenue / nominal * 100,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="政府支出与投资/GDP",
                series=(expense + capital) / nominal * 100,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
        ),
        series_groups={
            "财政与外部余额": pd.concat(
                [fiscal_ratio, current_ratio],
                axis=1,
            )
        },
        decomposition_tables={
            "一般政府财政拆解": fiscal_components,
            "经常账户拆解": external_components,
        },
        provenance=_provenance_subset(bundle, source_ids),
        methodology_notes=(
            "财政使用合并一般政府口径，不使用联邦预算代替。",
            "财政余额等于收入减经常支出和非金融资产净购置。",
            "经常账户等于货物、服务、初次收入和二次收入之和。",
        ),
    )


def build_monetary_panel(bundle: UAEDataBundle) -> MacroPanelResult:
    """固定汇率制度下的利率、流动性和信贷传导。"""

    fed = bundle.require_series("monetary.fed_iorb")
    base = bundle.require_series("monetary.cbuae_base_rate")
    eibor = bundle.require_series("monetary.eibor_3m")
    m1 = bundle.require_series("monetary.m1")
    m2 = bundle.require_series("monetary.m2")
    m3 = bundle.require_series("monetary.m3")
    deposits = bundle.require_series("banking.total_deposits")
    credit = bundle.require_series("banking.total_credit")
    private_credit = bundle.require_series("banking.private_credit")
    credit_yoy = _growth(credit, 12).rename("银行信贷同比")
    deposit_yoy = _growth(deposits, 12).rename("银行存款同比")
    m3_yoy = _growth(m3, 12).rename("M3同比")
    loan_deposit = (credit / deposits * 100).rename("贷存比")
    dfm = bundle.require_series("market.dfm_index")
    dfm_yoy = _growth(dfm, 252).rename("DFM同比")

    period, base_value = _latest(base)
    _, credit_value = _latest(credit_yoy)
    _, dfm_value = _latest(dfm_yoy)
    evidence = (
        _evidence(
            bundle=bundle,
            indicator_id="monetary.cbuae_base_rate",
            label="CBUAE基础利率",
            value=base_value,
            unit="%",
            evidence_class=EvidenceClass.MECHANISM,
        ),
        _evidence(
            bundle=bundle,
            indicator_id="banking.total_credit",
            label="银行信贷同比",
            value=credit_value,
            unit="%",
            evidence_class=EvidenceClass.MECHANISM,
        ),
        _evidence(
            bundle=bundle,
            indicator_id="market.dfm_index",
            label="DFM同比",
            value=dfm_value,
            unit="%",
            evidence_class=EvidenceClass.LEADING,
        ),
    )
    headline = build_diagnostic(
        title="货币、信贷与金融条件",
        result_sentence=(
            f"{_period_label(period)}CBUAE基础利率为{base_value:.2f}%。"
        ),
        accounting_sentence=(
            f"银行信贷同比变化{credit_value:.1f}%，"
            f"贷存比为{_latest(loan_deposit)[1]:.1f}%。"
        ),
        mechanism_sentence=(
            f"真实DFM指数同比变化{dfm_value:.1f}%，"
            "作为资产价格和风险偏好的交叉信号。"
        ),
        evidence=evidence,
        limitation=(
            "DFM为真实数据；利率、货币和银行序列为模拟数据，"
            "因此只能演示固定汇率传导框架。"
        ),
        accounting_complete=True,
    )
    source_ids = (
        "monetary.fed_iorb",
        "monetary.cbuae_base_rate",
        "monetary.eibor_3m",
        "monetary.m1",
        "monetary.m2",
        "monetary.m3",
        "banking.total_deposits",
        "banking.total_credit",
        "banking.private_credit",
        "banking.retail_credit",
        "market.dfm_index",
    )
    return MacroPanelResult(
        key="monetary",
        title="货币、信贷与金融条件",
        headline=headline,
        metrics=(
            _metric(
                label="CBUAE基础利率",
                series=base,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="3个月EIBOR",
                series=eibor,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="银行信贷同比",
                series=credit_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
            _metric(
                label="M3同比",
                series=m3_yoy,
                unit="%",
                kind=ProvenanceKind.SIMULATED,
            ),
        ),
        series_groups={
            "利率传导": pd.concat(
                [
                    fed.rename("美联储政策利率"),
                    base.rename("CBUAE基础利率"),
                    eibor.rename("3个月EIBOR"),
                ],
                axis=1,
            ),
            "货币总量": pd.concat(
                [m1.rename("M1"), m2.rename("M2"), m3.rename("M3")],
                axis=1,
            ),
            "存款与信贷": pd.concat(
                [
                    deposit_yoy,
                    credit_yoy,
                    _growth(private_credit, 12).rename("私营部门信贷同比"),
                ],
                axis=1,
            ),
            "资产价格信号": dfm_yoy.to_frame(),
        },
        decomposition_tables={
            "银行流动性": pd.concat(
                [
                    deposits.rename("存款"),
                    credit.rename("信贷"),
                    loan_deposit,
                ],
                axis=1,
            )
        },
        provenance=_provenance_subset(bundle, source_ids),
        methodology_notes=(
            "传导顺序为美联储利率、CBUAE基础利率、EIBOR、信贷和需求。",
            "M1、M2和M3保持层级可加关系。",
            "DFM是迪拜市场信号，不能代表全部金融资产。",
        ),
    )


def build_monitoring_dashboard(
    file_input: Any = DEFAULT_UAE_WORKBOOK,
) -> MonitoringDashboardResult:
    """构建总览所需的全部宏观结果系统。"""

    bundle = load_runtime_uae_bundle(file_input)
    panels = (
        build_growth_panel(bundle),
        build_inflation_panel(bundle),
        build_labor_panel(bundle),
        build_fiscal_external_panel(bundle),
        build_monetary_panel(bundle),
    )
    return MonitoringDashboardResult(
        panels={panel.key: panel for panel in panels}
    )

