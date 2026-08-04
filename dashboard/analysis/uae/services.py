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
from dashboard.analysis.uae.data_adapter import load_runtime_uae_bundle
from dashboard.analysis.uae.diagnostics import build_diagnostic
from dashboard.analysis.uae.growth import calculate_industry_diagnostics
from dashboard.analysis.uae.indicator_catalog import (
    INDUSTRY_NAMES,
    NOMINAL_INDUSTRY_IDS,
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


def _build_price_volume_series(
    bundle: UAEDataBundle,
    *,
    nominal_id: str,
    real_id: str,
    real_yoy_id: str,
    real_label: str,
    deflator_label: str,
) -> pd.DataFrame:
    """读取实际当季同比，并由现价与不变价水平构造平减指数。"""

    nominal = bundle.require_series(nominal_id)
    real = bundle.require_series(real_id)
    real_yoy = bundle.require_series(real_yoy_id)
    deflator = nominal.div(real).mul(100)
    deflator_yoy = deflator.div(deflator.shift(4)).sub(1).mul(100)
    prefix = (
        "【模拟】"
        if _derived_kind(bundle, (nominal_id, real_id, real_yoy_id))
        is ProvenanceKind.SIMULATED
        else "【真实】"
    )
    return pd.concat(
        [
            real_yoy.rename(f"{prefix}{real_label}"),
            deflator_yoy.rename(f"{prefix}{deflator_label}"),
        ],
        axis=1,
    ).dropna()


def _build_industry_price_volume_quadrant(
    *,
    nonoil_real_gdp: pd.Series,
    real_levels: dict[str, pd.Series],
    nominal_levels: dict[str, pd.Series],
) -> pd.DataFrame:
    """构造逐季度行业量价截面，并验证实际增加值占比核算闭合。"""

    real_frame = pd.DataFrame(real_levels)
    nominal_frame = pd.DataFrame(nominal_levels)
    aligned = pd.concat(
        [
            nonoil_real_gdp.rename("非油实际GDP"),
            real_frame.add_prefix("实际｜"),
            nominal_frame.add_prefix("现价｜"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    if aligned.empty:
        raise ValueError("行业量价四象限没有共同有效季度")

    real_frame = real_frame.reindex(aligned.index)
    nominal_frame = nominal_frame.reindex(aligned.index)
    nonoil = aligned["非油实际GDP"]
    if (real_frame <= 0).any().any() or (nominal_frame <= 0).any().any():
        raise ValueError("行业量价四象限要求现价和不变价增加值均为正数")
    if (nonoil <= 0).any():
        raise ValueError("行业量价四象限要求非油实际GDP为正数")

    real_growth = real_frame.div(real_frame.shift(4)).sub(1).mul(100)
    deflator = nominal_frame.div(real_frame).mul(100)
    deflator_growth = deflator.div(deflator.shift(4)).sub(1).mul(100)
    shares = real_frame.div(nonoil, axis=0)
    share_error = shares.sum(axis=1).sub(1).abs()
    max_share_error = float(share_error.max())
    if max_share_error > 1e-8:
        raise ValueError(
            "行业实际GDP占非油实际GDP比例未加总为1："
            f"最大误差为{max_share_error:.12g}"
        )

    snapshots: list[pd.DataFrame] = []
    for period in aligned.index:
        snapshot = pd.DataFrame(
            {
                "季度": _period_label(period),
                "行业": list(real_frame.columns),
                "实际增加值增速": real_growth.loc[period].to_numpy(),
                "行业隐含平减指数增速": (
                    deflator_growth.loc[period].to_numpy()
                ),
                "实际GDP占非油GDP比例": shares.loc[period].to_numpy(),
            }
        ).dropna()
        if len(snapshot) == len(real_frame.columns):
            snapshots.append(snapshot)
    if not snapshots:
        raise ValueError("行业量价四象限没有可计算同比增速的季度")
    return pd.concat(snapshots, ignore_index=True).set_index(["季度", "行业"])


def build_growth_panel(bundle: UAEDataBundle) -> MacroPanelResult:
    """GDP量价关系、部门拉动以及季度非油行业拉动。"""

    real_gdp = bundle.require_series("growth.real_gdp").dropna()
    nonoil = bundle.require_series("growth.nonoil_real_gdp").dropna()
    oil = (real_gdp - nonoil).rename("石油")

    price_volume_groups = {
        "实际GDP增速与GDP平减指数同比": _build_price_volume_series(
            bundle,
            nominal_id="growth.nominal_gdp",
            real_id="growth.real_gdp",
            real_yoy_id="growth.real_gdp_yoy",
            real_label="实际GDP当季同比",
            deflator_label="GDP平减指数同比",
        ),
        "非石油实际GDP增速与非石油GDP平减指数同比": _build_price_volume_series(
            bundle,
            nominal_id="growth.nonoil_nominal_gdp",
            real_id="growth.nonoil_real_gdp",
            real_yoy_id="growth.nonoil_real_gdp_yoy",
            real_label="非石油实际GDP当季同比",
            deflator_label="非石油GDP平减指数同比",
        ),
        "非金融公司实际增加值增速与平减指数同比": _build_price_volume_series(
            bundle,
            nominal_id="growth.nonfinancial_nominal_gdp",
            real_id="growth.nonfinancial_real_gdp",
            real_yoy_id="growth.nonfinancial_real_gdp_yoy",
            real_label="非金融公司实际增加值当季同比",
            deflator_label="非金融公司GDP平减指数同比",
        ),
    }

    industry_series = {
        INDUSTRY_NAMES[industry_id][1]: bundle.require_series(
            f"industry.{industry_id}.real"
        ).dropna()
        for industry_id in INDUSTRY_NAMES
    }
    nominal_industry_series = {
        INDUSTRY_NAMES[industry_id][1]: bundle.require_series(
            f"industry.{industry_id}.nominal"
        ).dropna()
        for industry_id in INDUSTRY_NAMES
    }
    industry_quadrant = _build_industry_price_volume_quadrant(
        nonoil_real_gdp=nonoil,
        real_levels=industry_series,
        nominal_levels=nominal_industry_series,
    )
    quarterly_nonoil = pd.concat(
        {"非油实际GDP": nonoil, **industry_series},
        axis=1,
        join="inner",
    ).dropna()
    quarterly_gap = (
        quarterly_nonoil["非油实际GDP"]
        - quarterly_nonoil[list(industry_series)].sum(axis=1)
    )
    max_quarterly_gap = float(quarterly_gap.abs().max())
    if max_quarterly_gap > 1e-5:
        raise ValueError(
            "非油行业季度加总不等于非油实际GDP："
            f"最大差额为{max_quarterly_gap:.6f}百万迪拉姆"
        )

    industry_diagnostics = calculate_industry_diagnostics(
        quarterly_nonoil["非油实际GDP"],
        {
            column: quarterly_nonoil[column]
            for column in industry_series
        },
        periods=4,
        absolute_tolerance=1e-5,
        relative_tolerance=1e-10,
    )
    industry_contributions = industry_diagnostics.contribution_result
    if not industry_contributions.additivity.within_tolerance.all():
        raise ValueError("季度非油行业加总未通过非油实际GDP一致性校验")

    raw_industry_pull = industry_contributions.contributions
    average_industry_shares = quarterly_nonoil[
        list(industry_series)
    ].div(
        quarterly_nonoil["非油实际GDP"],
        axis=0,
    ).mean()
    top_five_industries = list(
        average_industry_shares.nlargest(5).index
    )
    top_five_pull = raw_industry_pull[top_five_industries]
    other_pull = raw_industry_pull.drop(
        columns=top_five_industries
    ).sum(
        axis=1,
        min_count=1,
    ).rename("其他行业")

    total_growth = _growth(real_gdp, 4).rename("实际GDP同比")
    nonoil_growth = _growth(nonoil, 4).rename("非油GDP同比")
    oil_production_id = "oil.crude_production"
    oil_production = bundle.require_series(oil_production_id).dropna()
    oil_production_prefix = (
        "【模拟】"
        if bundle.is_simulated(oil_production_id)
        else "【真实】"
    )
    oil_production_yoy = _growth(oil_production, 4).rename(
        f"{oil_production_prefix}石油及其他液体产量季度同比"
    )
    nonoil_pull = (
        (nonoil - nonoil.shift(4))
        .div(real_gdp.shift(4))
        .mul(100)
        .rename("非石油经济部门拉动")
    )
    oil_pull = (
        (oil - oil.shift(4))
        .div(real_gdp.shift(4))
        .mul(100)
        .rename("石油经济部门拉动")
    )

    latest_contributions = (
        top_five_pull.dropna(how="all").iloc[-1]
    )
    top_name = latest_contributions.abs().idxmax()
    top_value = float(latest_contributions[top_name])
    driver_word = "拉动" if top_value >= 0 else "拖累"
    total_period, total_value = _latest(total_growth)
    nonoil_period, nonoil_value = _latest(nonoil_growth)

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
    )
    direction = "扩张" if total_value >= 0 else "收缩"
    headline = build_diagnostic(
        title="经济增长与结构",
        result_sentence=(
            f"实际GDP在{_period_label(total_period)}同比"
            f"{direction}{abs(total_value):.1f}%。"
        ),
        accounting_sentence=(
            f"最新季度非油行业核算中，{top_name}{driver_word}最大，"
            f"为{abs(top_value):.1f}个百分点；16个行业拉动之和等于非油GDP同比。"
        ),
        mechanism_sentence=(
            "行业拉动用于识别非油增长结构，不作为行业增长的因果机制证据。"
        ),
        evidence=evidence,
        limitation=(
            "行业拉动是基于不变价增加值的核算分解，"
            "说明增长来自哪些行业，不解释这些行业为何增长。"
        ),
        accounting_complete=True,
    )

    trend = pd.concat(
        [
            nonoil_pull.rename("【真实】非石油经济部门拉动"),
            oil_pull.rename("【真实】石油经济部门拉动"),
            oil_production_yoy,
        ],
        axis=1,
    ).reindex(real_gdp.index).dropna()
    quarterly_industry_pull = pd.concat(
        [
            top_five_pull,
            other_pull,
            industry_contributions.total_growth.rename(
                "【真实】非油GDP同比"
            ),
        ],
        axis=1,
    ).dropna(how="all")
    source_ids = (
        "growth.real_gdp",
        "growth.nominal_gdp",
        "growth.nonoil_real_gdp",
        "growth.nonoil_nominal_gdp",
        "growth.nonfinancial_real_gdp",
        "growth.nonfinancial_nominal_gdp",
        "growth.real_gdp_yoy",
        "growth.nonoil_real_gdp_yoy",
        "growth.nonfinancial_real_gdp_yoy",
        oil_production_id,
        *REAL_INDUSTRY_IDS,
        *NOMINAL_INDUSTRY_IDS,
    )
    return MacroPanelResult(
        key="growth",
        title="经济增长与结构",
        headline=headline,
        metrics=(),
        series_groups={
            **price_volume_groups,
            "GDP部门拉动与石油产量同比": trend,
            "非油实际GDP同比及行业拉动": quarterly_industry_pull,
            "行业量价四象限图": industry_quadrant,
            "行业扩张广度指数": industry_diagnostics.breadth,
            "行业增长集中度": industry_diagnostics.concentration,
            "行业增长持续性与状态矩阵": (
                industry_diagnostics.persistence
            ),
        },
        decomposition_tables={},
        provenance=_provenance_subset(bundle, source_ids),
        methodology_notes=(
            "GDP平减指数按现价GDP除以不变价GDP并乘以100构造，再计算季度同比增速。",
            "实际GDP当季同比直接读取指标字典中的不变价当季同比序列，不由GDP水平值重新计算。",
            "实际GDP同比与平减指数同比均为增长率，共用同一纵轴展示；两者仍不能直接相加。",
            "折线展示石油及其他液体产量的季度同比增速，并与GDP可用季度对齐。",
            "堆叠柱形分别使用非油和石油实际GDP同比增量除以上年同期总体实际GDP，单位为百分点。",
            "两部门拉动逐季度相加等于实际GDP同比增速。",
            "季度行业拉动使用各行业本季度与上年同季度的不变价增加值之差，除以上年同季度非油实际GDP，单位为百分点。",
            "在完整数据范围内逐季度计算各行业实际GDP占非油实际GDP的比例，并按季度占比的算术平均值固定选取前5个行业。",
            "前5个行业在所有季度保持不变，其余11个行业合并为“其他行业”。",
            "全部16个非油行业在季度层面加总等于非油实际GDP；柱形总高度与非油GDP同比折线一致，不设置残差。",
            "行业隐含平减指数按各行业现价增加值除以不变价增加值并乘以100构造；横纵轴均使用季度同比增速。",
            "气泡面积表示行业实际GDP占当季非油实际GDP比例；每个季度16个行业占比之和必须在1e-8容差内等于1。",
            "四象限动画对所有季度使用固定坐标范围、固定行业颜色和统一气泡面积尺度，保证跨期视觉可比。",
            "行业广度后台保留等权与加权派生结果；图表仅展示不加权的正增长行业比例和连续四季度正增长行业比例。",
            "行业增长集中度地图对16个行业的正负贡献绝对值统一归一化，不再只对正向贡献计算HHI。",
            "贡献平衡指数为行业净贡献除以贡献绝对值合计并乘100；负值表示拖累占主导，0表示完全抵消，正值表示拉动占主导。",
            "绝对贡献HHI按固定16行业标准化到0—100；0对应16行业等额变动，100对应单一行业主导。",
            "气泡面积使用全部行业贡献绝对值合计，悬浮信息报告非油GDP同比和最大正负贡献行业；行业贡献缺失或全部为0时不绘制。",
            "集中度图使用Plotly季度帧和图内时间轴：淡色气泡保留截至所选季度的历史，深色描边气泡突出当前季度，并支持从头播放和暂停。",
            "集中度纵轴理论范围为0—100；显示上限按完整样本最大值留出20%余量后向上取整，最低20、最高100，且所有季度帧共用固定范围。",
            "行业状态以当季增速相对截至上季的自身历史均值判断高低，以当季同比相对上季度同比判断加速、放缓或改善、恶化。",
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
    dubai_kind = bundle.require_provenance(
        "oil.dubai_crude_price"
    ).kind
    dubai_tag = (
        "【模拟】"
        if dubai_kind is ProvenanceKind.SIMULATED
        else "【真实】"
    )
    dubai_yoy = _growth(
        bundle.require_series("oil.dubai_crude_price"),
        12,
    ).rename(f"{dubai_tag}迪拜原油同比")
    mechanism = pd.concat([housing_yoy, wage_yoy, dubai_yoy], axis=1)

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
        limitation=(
            "CPI与WPS指标为运行时模拟数据；"
            "迪拜原油价格按照上传工作簿或模拟补位的来源标识展示。"
        ),
        accounting_complete=True,
    )
    source_ids = (
        "inflation.cpi_all",
        *category_ids,
        "labor.wps_average_wage",
        "oil.dubai_crude_price",
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
    file_input: Any,
) -> MonitoringDashboardResult:
    """基于显式传入的工作簿构建五个宏观主题结果。"""

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
