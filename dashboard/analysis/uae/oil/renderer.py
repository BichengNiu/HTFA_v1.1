"""阿联酋石油市场与财政收入监测面板。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.periods import (
    common_latest_month,
    within_month_window,
)
from dashboard.analysis.uae.oil.charts import (
    MARKET_PRODUCTION_LABEL,
    MARKET_RIG_COUNT_LABEL,
    REVENUE_LABEL,
    REVENUE_PRICE_LABEL,
    build_oil_market_figure,
    build_oil_revenue_figure,
    build_war_pressure_index_figure,
    build_war_pressure_raw_figure,
)
from dashboard.analysis.uae.oil.data import OilMarketData, load_oil_market_data
from dashboard.analysis.uae.oil.revenue import (
    PRICE_BENCHMARK_COLUMN,
    REVENUE_PRICE_BENCHMARK,
    REVENUE_COLUMN,
    YOY_COLUMN,
    YTD_COLUMN,
    YTD_YOY_COLUMN,
    estimate_monthly_oil_revenue,
)
from dashboard.analysis.uae.oil.war_pressure import (
    BALLISTIC_LABEL,
    CRUISE_LABEL,
    PRESSURE_LABEL,
    RAW_LABELS,
    UAV_LABEL,
    WarPressureData,
    load_war_pressure_data,
)
from dashboard.analysis.uae.plot_helpers import translate_source_text
from dashboard.analysis.uae.metrics import (
    format_count_value,
    format_scaled_value,
)
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

OIL_FISCAL_EXPLANATION = """
- **油价**：布伦特期货由洲际交易所发布、布伦特现货由金联创发布；原始数据为日度/周度价格（美元/桶），油价卡片按原始频率显示最新观测，反映国际原油价格。
- **原油产量**：由欧佩克发布；原始数据为月度阿联酋原油产量（桶/天），反映原油生产规模。
- **活跃钻机数**：由贝克休斯发布；原始数据按月份、地区及陆上/海上拆分，汇总为阿联酋月度活跃钻机数（台），反映石油勘探开发活动。
- **月度石油收入（估算）**：由金联创、欧佩克发布；布伦特现货为日度/周度价格，按自然月取月均值；阿联酋原油产量为月度数据，按月取有效观测均值后按
  `价格 × 产量 × 当月天数 ÷ 1亿` 计算（亿美元）；价格或产量缺失时不估算，作为销售收入规模代理。
- **同比与累计**：原始数据为上述月度估算收入；月度同比为本月收入与上年同月之比减1，年度累计为年内各月收入之和，
  年度累计同比为本年累计与上年同期累计之比减1。
- **价格/产量拉动率**：原始数据为上述月度价格、产量和收入；用中点法计算
  `(ΔP·V̄ + ΔV·P̄) ÷ (P₋₁₂·V₋₁₂)`，其中 `P̄=(P+P₋₁₂)/2`、`V̄=(V+V₋₁₂)/2`，
  判断收入变化主要由价格还是产量驱动。
""".strip()

WAR_PRESSURE_EXPLANATION = """
- **原始数据**：由“根据公开新闻整理”汇编；原始数据为日度弹道导弹、巡航导弹和无人机数量；月度武器数量为各日数量按月求和，反映公开登记的袭击活动。
- **战争压力指数**：原始数据为上述日度数量；按 `9×log1p(弹道导弹数量)+3×log1p(巡航导弹数量)+log1p(无人机数量)` 加权后按月求和，
  再在战争观测窗口内做 min-max 归一化 `100×(当月值−最小值)÷(最大值−最小值)`。
  `log1p(x)=ln(1+x)` 用于压缩极端值；指数越高表示登记袭击强度相对越高，最高月为100、最低月为0。
- **边界**：该指数是公开登记数量的袭击强度代理，不等同于实际经济损失、人员伤亡或综合安全风险；未分类、漏报和覆盖变化会影响比较。
""".strip()


def _source_payload() -> tuple[bytes, str] | None:
    """返回当前会话上传的共享工作簿。"""

    shared_file = get_shared_dataset_file()
    if shared_file is None:
        return None
    content = (
        shared_file.getvalue()
        if hasattr(shared_file, "getvalue")
        else shared_file.read()
    )
    name = Path(str(getattr(shared_file, "name", "阿联酋.xlsx"))).name
    return content, name


def _load_oil_market_cached(content: bytes, file_name: str) -> OilMarketData:
    return load_oil_market_data(content, file_name=file_name)


def _latest_change(
    series: pd.Series,
    *,
    days: int | None = None,
) -> tuple[float, pd.Timestamp, float | None]:
    clean = series.dropna().sort_index()
    latest_date = pd.Timestamp(clean.index[-1])
    latest_value = float(clean.iloc[-1])
    if days is None:
        base = clean.iloc[-2] if len(clean) >= 2 else None
    else:
        history = clean.loc[: latest_date - pd.Timedelta(days=days)]
        base = history.iloc[-1] if not history.empty else None
    if base is None or float(base) == 0:
        return latest_value, latest_date, None
    return latest_value, latest_date, (latest_value / float(base) - 1) * 100


def _metric_delta(label: str, change: float | None) -> str | None:
    return None if change is None else f"{label} {change:+.1f}%"


def _render_oil_metrics(st_obj: Any, data: OilMarketData) -> None:
    columns = st_obj.columns(4)
    price_names = ("布伦特期货", "布伦特现货")
    for column, name in zip(columns[:2], price_names):
        value, as_of, change = _latest_change(data.prices[name], days=30)
        metadata = data.metadata[name]
        with column:
            st_obj.metric(
                name,
                format_scaled_value(value, "美元/桶"),
                delta=_metric_delta("30日", change),
                delta_color="off",
                help=(
                    f"截至 {as_of:%Y-%m-%d}；{metadata.frequency}；"
                    f"来源：{translate_source_text(metadata.source)}；"
                    f"源表更新：{metadata.updated_at}"
                ),
            )

    value, as_of, change = _latest_change(data.production)
    metadata = data.metadata[data.production.name]
    with columns[2]:
        st_obj.metric(
            "阿联酋原油产量",
            format_count_value(value, "桶/天"),
            delta=_metric_delta("环比", change),
            delta_color="off",
            help=(
                f"截至 {as_of:%Y-%m}；月度；来源："
                f"{translate_source_text(metadata.source)}；"
                f"源表更新：{metadata.updated_at}"
            ),
        )

    if data.rig_count is None or data.rig_count.dropna().empty:
        with columns[3]:
            st_obj.metric("阿联酋石油活跃钻机数", "—")
        return

    value, as_of, change = _latest_change(data.rig_count)
    metadata = data.metadata[data.rig_count.name]
    with columns[3]:
        st_obj.metric(
            "阿联酋石油活跃钻机数",
            format_count_value(value, "台"),
            delta=_metric_delta("环比", change),
            delta_color="off",
            help=(
                f"截至 {as_of:%Y-%m}；月度；来源："
                f"{translate_source_text(metadata.source)}；"
                f"源表更新：{metadata.updated_at}"
            ),
        )


def _render_revenue_metrics(st_obj: Any, revenue: pd.DataFrame) -> None:
    latest = revenue.iloc[-1]
    latest_date = pd.Timestamp(revenue.index[-1])
    columns = st_obj.columns(4)
    with columns[0]:
        st_obj.metric(
            "最新月估算石油收入",
            f"{latest[REVENUE_COLUMN]:,.2f} 亿美元",
            help=(
                f"截至 {latest_date:%Y-%m}；价格基准："
                f"{latest[PRICE_BENCHMARK_COLUMN]}"
            ),
        )
    with columns[1]:
        st_obj.metric(
            f"{latest_date.year} 年石油累计收入",
            f"{latest[YTD_COLUMN]:,.2f} 亿美元",
        )
    with columns[2]:
        value = latest[YOY_COLUMN]
        st_obj.metric("石油收入月度同比", f"{value:+.1f}%" if pd.notna(value) else "—")
    with columns[3]:
        value = latest[YTD_YOY_COLUMN]
        st_obj.metric(
            "石油收入年度累计同比",
            f"{value:+.1f}%" if pd.notna(value) else "—",
        )


def _render_war_pressure_metrics(
    st_obj: Any,
    data: WarPressureData,
) -> None:
    """展示最新完整月份的三类武器数量与战争压力指数。"""

    latest_values = data.values.dropna(
        subset=[*RAW_LABELS, PRESSURE_LABEL]
    ).sort_index()
    if latest_values.empty:
        st_obj.info("战争压力数据没有完整的最新月份。")
        return

    latest = latest_values.iloc[-1]
    latest_date = pd.Timestamp(latest_values.index[-1])
    source_text = "、".join(
        dict.fromkeys(
            metadata.source for metadata in data.metadata.values() if metadata.source
        )
    )
    help_text = (
        f"截至 {latest_date:%Y-%m}；月度_WAM；"
        f"来源：{translate_source_text(source_text)}"
    )
    columns = st_obj.columns(4)
    metric_specs = (
        ("最新月弹道导弹", latest[BALLISTIC_LABEL], "枚"),
        ("最新月巡航导弹", latest[CRUISE_LABEL], "枚"),
        ("最新月无人机", latest[UAV_LABEL], "架"),
    )
    for column, (label, value, unit) in zip(columns[:3], metric_specs):
        with column:
            st_obj.metric(
                label,
                format_count_value(float(value), unit),
                help=help_text,
            )
    with columns[3]:
        st_obj.metric(
            "最新月战争压力指数",
            format_scaled_value(float(latest[PRESSURE_LABEL]), "指数"),
            help=(
                f"{help_text}；原始压力为每日 9×弹道 log1p + 3×巡航 log1p + 无人机 log1p 后按月汇总，"
                "再按战争期间 min-max 归一化到 0–100（不累计）"
            ),
        )


def _render_war_pressure_section(
    st_obj: Any,
    data: WarPressureData,
) -> None:
    """在石油收入之前展示 WAM 原始数据与战争压力指数。"""

    source_text = "、".join(
        dict.fromkeys(
            metadata.source for metadata in data.metadata.values() if metadata.source
        )
    )
    values = data.values.loc[:, [*RAW_LABELS, PRESSURE_LABEL]].sort_index()
    columns = st_obj.columns(2, gap="small")
    with columns[0]:
        render_pyplot_figure(
            st_obj,
            build_war_pressure_raw_figure(values, source_text),
            bbox_inches=None,
            place_legend_bottom=False,
        )
    with columns[1]:
        render_pyplot_figure(
            st_obj,
            build_war_pressure_index_figure(values, source_text),
            bbox_inches=None,
            place_legend_bottom=False,
        )
    render_chart_download(
        st_obj,
        values,
        title="战争压力（月度_WAM）",
        key="analysis.uae.oil.war_pressure.download",
    )
    with st_obj.expander("指标算法与解读", expanded=True):
        st_obj.markdown(WAR_PRESSURE_EXPLANATION)
    st_obj.divider()


def _render_charts(
    st_obj: Any,
    data: OilMarketData,
    revenue: pd.DataFrame,
) -> None:
    production_source = data.metadata[data.production.name].source
    rig_count_source = (
        None
        if data.rig_count is None
        else data.metadata[data.rig_count.name].source
    )
    market_sources = "、".join(
        dict.fromkeys(
            source
            for source in (production_source, rig_count_source)
            if source
        )
    )
    revenue_sources = "、".join(
        dict.fromkeys((data.metadata["布伦特现货"].source, production_source))
    )
    columns = st_obj.columns(2, gap="small")
    market_cutoff_series = [(data.production.name, data.production)]
    if data.rig_count is not None and not data.rig_count.dropna().empty:
        market_cutoff_series.append((data.rig_count.name, data.rig_count))
    market_last_month = common_latest_month(market_cutoff_series)
    market_first_month = market_last_month - 36
    market_production = within_month_window(
        data.production,
        first_month=market_first_month,
        last_month=market_last_month,
    )
    market_rig_count = (
        None
        if data.rig_count is None
        else within_month_window(
            data.rig_count,
            first_month=market_first_month,
            last_month=market_last_month,
        )
    )
    market_series = [
        market_production.div(10_000).rename("阿联酋原油产量（万桶/天）"),
    ]
    if market_rig_count is not None:
        market_series.append(
            market_rig_count.rename("阿联酋石油活跃钻机数（台）")
        )
    market_download = pd.concat(
        market_series,
        axis=1,
    ).sort_index()
    revenue_cutoff_series = [(REVENUE_COLUMN, revenue[REVENUE_COLUMN])]
    revenue_last_month = common_latest_month(revenue_cutoff_series)
    revenue_download = within_month_window(
        revenue,
        first_month=revenue_last_month - 36,
        last_month=revenue_last_month,
    )
    with columns[0]:
        render_pyplot_figure(
            st_obj,
            build_oil_market_figure(
                market_production,
                market_sources,
                market_rig_count,
                units={
                    MARKET_PRODUCTION_LABEL: "万桶/天",
                    **(
                        {
                            MARKET_RIG_COUNT_LABEL: data.metadata[
                                data.rig_count.name
                            ].unit
                        }
                        if data.rig_count is not None
                        else {}
                    ),
                },
            ),
            bbox_inches=None,
            place_legend_bottom=False,
        )
        render_chart_download(
            st_obj,
            market_download,
            title="原油产量与活动钻机数",
            key="analysis.uae.oil.market.download",
        )
    with columns[1]:
        render_pyplot_figure(
            st_obj,
            build_oil_revenue_figure(
                revenue_download,
                revenue_sources,
                units={
                    REVENUE_PRICE_LABEL: data.metadata[
                        REVENUE_PRICE_BENCHMARK
                    ].unit,
                    REVENUE_LABEL: "亿美元",
                },
            ),
            bbox_inches=None,
            place_legend_bottom=False,
        )
        render_chart_download(
            st_obj,
            revenue_download,
            title="石油价格与阿联酋石油收入",
            key="analysis.uae.oil.revenue.download",
        )


def render_oil_fiscal_panel(st_obj: Any = st) -> dict[str, Any]:
    """用真实油价和产量估算石油收入，不生成占位渠道。"""

    payload = _source_payload()
    if payload is None:
        st_obj.subheader("战争压力")
        st_obj.subheader("石油生产与收入")
        message = "当前工作簿不可用，无法读取真实油价与原油产量。"
        st_obj.info(message)
        return {"status": "no_data", "message": message}

    war_pressure_available = False
    try:
        content, file_name = payload
        with st_obj.spinner("正在读取日度油价与月度原油产量..."):
            data = _load_oil_market_cached(content, file_name)
        try:
            war_pressure = load_war_pressure_data(content, file_name=file_name)
        except (KeyError, TypeError, ValueError) as exc:
            st_obj.subheader("战争压力")
            st_obj.warning(f"战争压力数据暂不可用：{exc}")
        else:
            st_obj.subheader("战争压力")
            _render_war_pressure_metrics(st_obj, war_pressure)
            _render_war_pressure_section(st_obj, war_pressure)
            war_pressure_available = True
        st_obj.subheader("石油生产与收入")
        _render_oil_metrics(st_obj, data)
        revenue = estimate_monthly_oil_revenue(data.prices, data.production)
        _render_revenue_metrics(st_obj, revenue)
        _render_charts(st_obj, data, revenue)
        with st_obj.expander("指标算法与解读", expanded=True):
            st_obj.markdown(OIL_FISCAL_EXPLANATION)
        from dashboard.analysis.uae.government_finance import (
            render_government_finance_section,
        )

        government_finance = render_government_finance_section(
            st_obj,
            content,
            file_name,
        )
        from dashboard.analysis.uae.real_estate import (
            render_real_estate_section,
        )

        real_estate = render_real_estate_section(st_obj, content, file_name)
        from dashboard.analysis.uae.transport import (
            render_transport_section,
        )

        transport = render_transport_section(st_obj, content, file_name)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.error(f"油价与产量数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {
        "status": "success",
        "source": file_name,
        "war_pressure": war_pressure_available,
        "government_finance": government_finance,
        "real_estate": real_estate,
        "transport": transport,
    }


__all__ = ["render_oil_fiscal_panel"]
