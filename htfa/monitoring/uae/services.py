"""阿联酋宏观监测的分析服务。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from htfa.monitoring.uae.contracts import (
    DataProvenance,
    EvidenceClass,
    EvidenceItem,
    ProvenanceKind,
    UAEDataBundle,
)
from htfa.monitoring.uae.data_adapter import load_real_uae_bundle
from htfa.monitoring.uae.diagnostics import build_diagnostic
from htfa.monitoring.uae.growth import calculate_industry_diagnostics
from htfa.monitoring.uae.indicator_catalog import (
    INDUSTRY_NAMES,
    NOMINAL_INDUSTRY_IDS,
    REAL_INDUSTRY_IDS,
)
from htfa.monitoring.uae.results import (
    MacroPanelResult,
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
        sort=False,
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
        INDUSTRY_NAMES[industry_id].display_name: bundle.require_series(
            f"industry.{industry_id}.real"
        ).dropna()
        for industry_id in INDUSTRY_NAMES
    }
    nominal_industry_series = {
        INDUSTRY_NAMES[industry_id].display_name: bundle.require_series(
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
        sort=False,
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


def build_monitoring_dashboard(
    file_input: Any,
) -> MonitoringDashboardResult:
    """基于显式传入的工作簿构建宏观监测结果。"""

    try:
        bundle = load_real_uae_bundle(file_input)
        panels = {"growth": build_growth_panel(bundle)}
        unavailable: dict[str, str] = {}
    except ValueError as exc:
        panels = {}
        unavailable = {"growth": str(exc)}
    return MonitoringDashboardResult(
        panels=panels,
        unavailable_panels=unavailable,
    )
