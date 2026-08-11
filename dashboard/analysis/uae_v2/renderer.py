"""阿联酋高频经济监测 V2 的 Streamlit 展示骨架。"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae_v2.config import CHANNELS, ChannelSpec
from dashboard.analysis.uae_v2.oil_charts import (
    build_oil_market_figure,
    build_oil_revenue_figure,
)
from dashboard.analysis.uae_v2.oil_data import (
    OilMarketData,
    load_oil_market_data,
)
from dashboard.analysis.uae_v2.oil_revenue import (
    MOM_COLUMN,
    PRICE_BENCHMARK_COLUMN,
    REVENUE_COLUMN,
    YOY_COLUMN,
    YTD_COLUMN,
    estimate_monthly_oil_revenue,
)
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file


_PAGE_STYLES = """
<style>
.uae-v2-flow {
    display: flex;
    align-items: stretch;
    gap: 0.35rem;
    overflow-x: auto;
    padding: 0.45rem 0 1rem 0;
}
.uae-v2-node {
    min-width: 118px;
    flex: 1 0 118px;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 64px;
    padding: 0.6rem 0.7rem;
    border: 1px solid rgba(49, 130, 206, 0.30);
    border-radius: 8px;
    background: rgba(49, 130, 206, 0.07);
    font-size: 0.88rem;
    font-weight: 600;
    line-height: 1.3;
    text-align: center;
}
.uae-v2-arrow {
    display: flex;
    align-items: center;
    color: #718096;
    font-size: 1.1rem;
}
.uae-v2-placeholder {
    min-height: 190px;
    border: 1px dashed rgba(113, 128, 150, 0.55);
    border-radius: 10px;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    background: rgba(113, 128, 150, 0.04);
}
.uae-v2-placeholder-title {
    font-weight: 650;
    margin-bottom: 0.35rem;
}
.uae-v2-placeholder-note {
    color: #718096;
    font-size: 0.85rem;
}
</style>
"""


def _render_transmission_chain(st_obj: Any, steps: tuple[str, ...]) -> None:
    """以可横向滚动的节点流展示一条传导链。"""

    elements: list[str] = []
    for index, step in enumerate(steps):
        if index:
            elements.append('<div class="uae-v2-arrow">→</div>')
        elements.append(f'<div class="uae-v2-node">{escape(step)}</div>')
    st_obj.markdown(
        f'<div class="uae-v2-flow">{"".join(elements)}</div>',
        unsafe_allow_html=True,
    )


def _render_indicator_cards(st_obj: Any, channel: ChannelSpec) -> None:
    """展示本传导链优先接入的四个核心指标。"""

    st_obj.markdown("#### 核心高频指标")
    columns = st_obj.columns(4)
    for column, indicator in zip(columns, channel.indicators[:4]):
        with column:
            st_obj.metric(
                indicator.name,
                "—",
                help=f"频率：{indicator.frequency}；来源：{indicator.source}",
            )
            st_obj.caption(f"{indicator.frequency} · {indicator.source} · 待接入")


def _source_payload() -> tuple[bytes, str, str] | None:
    """返回当前会话上传的共享工作簿；未上传时不提供数据。"""

    shared_file = get_shared_dataset_file()
    if shared_file is None:
        return None
    if hasattr(shared_file, "getvalue"):
        content = shared_file.getvalue()
    else:
        content = shared_file.read()
    name = Path(str(getattr(shared_file, "name", "阿联酋.xlsx"))).name
    return content, name, "共享上传"


@st.cache_data(show_spinner=False)
def _load_oil_market_cached(content: bytes, file_name: str) -> OilMarketData:
    """按文件内容缓存油价与产量的窄范围解析结果。"""

    return load_oil_market_data(content, file_name=file_name)


def _latest_change(
    series: pd.Series,
    *,
    days: int | None = None,
) -> tuple[float, pd.Timestamp, float | None]:
    """返回最新值、最新日期和相对比较期的百分比变化。"""

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
    change = (latest_value / float(base) - 1) * 100
    return latest_value, latest_date, change


def _metric_delta(label: str, change: float | None) -> str | None:
    if change is None:
        return None
    return f"{label} {change:+.1f}%"


def _render_oil_metrics(st_obj: Any, data: OilMarketData) -> None:
    """展示油价基准和原油产量的最新值。"""

    st_obj.markdown("#### 油价与产量概览")
    columns = st_obj.columns(5)
    price_names = ("布伦特期货", "布伦特现货", "迪拜现货", "穆尔班现货")
    for column, name in zip(columns[:4], price_names):
        value, as_of, change = _latest_change(data.prices[name], days=30)
        metadata = data.metadata[name]
        with column:
            st_obj.metric(
                name,
                f"{value:,.2f} 美元/桶",
                delta=_metric_delta("30日", change),
                delta_color="off",
                help=(
                    f"截至 {as_of:%Y-%m-%d}；{metadata.frequency}；"
                    f"来源：{metadata.source}；源表更新：{metadata.updated_at}"
                ),
            )

    production_value, production_as_of, production_change = _latest_change(
        data.production
    )
    production_metadata = data.metadata[data.production.name]
    with columns[4]:
        st_obj.metric(
            "阿联酋原油产量",
            f"{production_value / 10_000:,.1f} 万桶/天",
            delta=_metric_delta("环比", production_change),
            delta_color="off",
            help=(
                f"截至 {production_as_of:%Y-%m}；月度；"
                f"来源：{production_metadata.source}；"
                f"源表更新：{production_metadata.updated_at}"
            ),
        )


def _render_oil_revenue_metrics(
    st_obj: Any,
    revenue: pd.DataFrame,
) -> None:
    """展示最新月收入、本年度累计、环比和同比。"""

    latest = revenue.iloc[-1]
    latest_date = pd.Timestamp(revenue.index[-1])
    benchmark = str(latest[PRICE_BENCHMARK_COLUMN])
    columns = st_obj.columns(4)
    with columns[0]:
        st_obj.metric(
            "最新月估算石油收入",
            f"{latest[REVENUE_COLUMN]:,.2f} 亿美元",
            help=f"截至 {latest_date:%Y-%m}；价格基准：{benchmark}",
        )
    with columns[1]:
        st_obj.metric(
            f"{latest_date.year} 年累计收入",
            f"{latest[YTD_COLUMN]:,.2f} 亿美元",
            help=f"本年度截至 {latest_date:%Y-%m} 的月度估算收入之和",
        )
    with columns[2]:
        st_obj.metric(
            "月度环比",
            (
                f"{latest[MOM_COLUMN]:+.1f}%"
                if pd.notna(latest[MOM_COLUMN])
                else "—"
            ),
        )
    with columns[3]:
        st_obj.metric(
            "月度同比",
            (
                f"{latest[YOY_COLUMN]:+.1f}%"
                if pd.notna(latest[YOY_COLUMN])
                else "—"
            ),
        )


def _render_oil_charts(
    st_obj: Any,
    data: OilMarketData,
    revenue: pd.DataFrame,
) -> None:
    """渲染油价、产量及估算石油收入。"""

    latest_date = pd.Timestamp(revenue.index.max())
    cutoff = latest_date - pd.DateOffset(years=3)
    prices = data.prices.loc[data.prices.index >= cutoff]
    production = data.production.loc[data.production.index >= cutoff]
    filtered_revenue = revenue.loc[revenue.index >= cutoff]
    production_source = data.metadata[data.production.name].source
    market_source_text = "、".join(
        dict.fromkeys(
            (
                data.metadata["布伦特现货"].source,
                production_source,
            )
        )
    )
    revenue_source_text = "、".join(
        dict.fromkeys(
            (
                data.metadata["穆尔班现货"].source,
                data.metadata["迪拜现货"].source,
                data.metadata["布伦特现货"].source,
                production_source,
            )
        )
    )
    chart_columns = st_obj.columns(2, gap="small")
    with chart_columns[0]:
        market_figure = build_oil_market_figure(
            prices,
            production,
            market_source_text,
        )
        st_obj.pyplot(
            market_figure,
            width="stretch",
            clear_figure=True,
        )
    with chart_columns[1]:
        revenue_figure = build_oil_revenue_figure(
            filtered_revenue,
            revenue_source_text,
        )
        st_obj.pyplot(
            revenue_figure,
            width="stretch",
            clear_figure=True,
        )

def _render_chart_placeholder(st_obj: Any, title: str) -> None:
    """渲染后续真实图表的稳定占位区。"""

    st_obj.markdown(
        (
            '<div class="uae-v2-placeholder">'
            f'<div class="uae-v2-placeholder-title">{escape(title)}</div>'
            '<div class="uae-v2-placeholder-note">'
            "图表区域已预留 · 等待真实数据接入"
            "</div></div>"
        ),
        unsafe_allow_html=True,
    )


def _render_indicator_inventory(
    st_obj: Any,
    channel: ChannelSpec,
    *,
    connected_indicators: set[str] | None = None,
) -> None:
    """展示指标频率、来源和当前接入状态。"""

    connected_indicators = connected_indicators or set()
    rows = [
        {
            "指标": indicator.name,
            "频率": indicator.frequency,
            "数据机构": indicator.source,
            "接入状态": (
                "已接入" if indicator.name in connected_indicators else "待接入"
            ),
        }
        for indicator in channel.indicators
    ]
    st_obj.dataframe(rows, hide_index=True, width="stretch")

    unique_sources: dict[tuple[str, str | None], None] = {}
    for indicator in channel.indicators:
        unique_sources[(indicator.source, indicator.source_url)] = None
    source_links = " · ".join(
        (
            f"[{escape(source)}]({url})"
            if url
            else escape(source)
        )
        for source, url in unique_sources
    )
    st_obj.caption("公开数据入口：")
    st_obj.markdown(source_links)


def _render_channel(st_obj: Any, channel: ChannelSpec) -> None:
    """渲染单个传导链 Tab 的完整展示骨架。"""

    st_obj.subheader(channel.title)
    st_obj.caption(channel.objective)
    oil_data = None
    oil_revenue = None
    if channel.key == "oil_fiscal":
        payload = _source_payload()
        if payload is None:
            st_obj.info("请先在侧边栏上传阿联酋工作簿以查看真实监测数据。")
            _render_indicator_cards(st_obj, channel)
        else:
            try:
                content, file_name, _ = payload
                with st_obj.spinner("正在读取日度油价与月度原油产量..."):
                    oil_data = _load_oil_market_cached(content, file_name)
                _render_oil_metrics(st_obj, oil_data)
                oil_revenue = estimate_monthly_oil_revenue(
                    oil_data.prices,
                    oil_data.production,
                )
                st_obj.markdown("#### 估算石油收入")
                _render_oil_revenue_metrics(st_obj, oil_revenue)
            except Exception as exc:  # noqa: BLE001 - 页面边界展示具体数据错误
                st_obj.error(f"油价与产量数据加载失败：{exc}")
                _render_indicator_cards(st_obj, channel)
    else:
        _render_indicator_cards(st_obj, channel)

    if channel.key != "oil_fiscal":
        st_obj.markdown("#### 传导路径")
        _render_transmission_chain(st_obj, channel.transmission)

    if oil_data is not None and oil_revenue is not None:
        _render_oil_charts(st_obj, oil_data, oil_revenue)
    else:
        chart_columns = st_obj.columns(2)
        for column, chart_title in zip(chart_columns, channel.chart_slots):
            with column:
                _render_chart_placeholder(st_obj, chart_title)

    if channel.key == "oil_fiscal":
        st_obj.divider()
        st_obj.subheader("Part 2 政府及政府控股企业现金流")
    else:
        with st_obj.expander("指标接入清单与公开来源", expanded=False):
            _render_indicator_inventory(st_obj, channel)


def render_uae_v2_monitoring(st_obj: Any = st) -> dict[str, Any]:
    """渲染阿联酋 V2 七条高频传导链页面。"""

    st_obj.markdown(_PAGE_STYLES, unsafe_allow_html=True)
    st_obj.title("阿联酋高频经济监测 V2")
    st_obj.caption(
        "从外部冲击出发，沿七条传导渠道追踪中观行业、企业与居民行为，"
        "最终验证非油 GDP、通胀和金融稳定。"
    )
    st_obj.info(
        "已接入石油—财政渠道的日度/周度油价、月度原油产量和估算石油收入；"
        "其余指标仍为展示框架，不生成模拟数据。"
    )

    tabs = st_obj.tabs([channel.tab_label for channel in CHANNELS])
    for tab, channel in zip(tabs, CHANNELS):
        with tab:
            _render_channel(st_obj, channel)

    return {
        "status": "success",
        "version": "v2",
        "tab_count": len(CHANNELS),
        "data_status": "oil_price_production_and_revenue_connected",
    }


__all__ = ["render_uae_v2_monitoring"]
