"""阿联酋石油市场与财政收入监测面板。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.oil.charts import (
    build_oil_market_figure,
    build_oil_revenue_figure,
)
from dashboard.analysis.uae.oil.data import OilMarketData, load_oil_market_data
from dashboard.analysis.uae.oil.revenue import (
    MOM_COLUMN,
    PRICE_BENCHMARK_COLUMN,
    REVENUE_COLUMN,
    YOY_COLUMN,
    YTD_COLUMN,
    estimate_monthly_oil_revenue,
)
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file


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


@st.cache_data(show_spinner=False)
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

    value, as_of, change = _latest_change(data.production)
    metadata = data.metadata[data.production.name]
    with columns[4]:
        st_obj.metric(
            "阿联酋原油产量",
            f"{value / 10_000:,.1f} 万桶/天",
            delta=_metric_delta("环比", change),
            delta_color="off",
            help=(
                f"截至 {as_of:%Y-%m}；月度；来源：{metadata.source}；"
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
            f"{latest_date.year} 年累计收入",
            f"{latest[YTD_COLUMN]:,.2f} 亿美元",
        )
    with columns[2]:
        value = latest[MOM_COLUMN]
        st_obj.metric("月度环比", f"{value:+.1f}%" if pd.notna(value) else "—")
    with columns[3]:
        value = latest[YOY_COLUMN]
        st_obj.metric("月度同比", f"{value:+.1f}%" if pd.notna(value) else "—")


def _render_charts(
    st_obj: Any,
    data: OilMarketData,
    revenue: pd.DataFrame,
) -> None:
    cutoff = pd.Timestamp(revenue.index.max()) - pd.DateOffset(years=3)
    production_source = data.metadata[data.production.name].source
    rig_count_source = (
        None
        if data.rig_count is None
        else data.metadata[data.rig_count.name].source
    )
    market_sources = "、".join(
        dict.fromkeys(
            source
            for source in (
                data.metadata["布伦特现货"].source,
                production_source,
                rig_count_source,
            )
            if source
        )
    )
    revenue_sources = "、".join(
        dict.fromkeys((data.metadata["布伦特现货"].source, production_source))
    )
    columns = st_obj.columns(2, gap="small")
    market_prices = data.prices.loc[data.prices.index >= cutoff]
    market_production = data.production.loc[data.production.index >= cutoff]
    market_rig_count = (
        None
        if data.rig_count is None
        else data.rig_count.loc[data.rig_count.index >= cutoff]
    )
    market_series = [
        market_prices["布伦特现货"].rename("布伦特原油现货价（美元/桶）"),
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
    revenue_download = revenue.loc[revenue.index >= cutoff]
    with columns[0]:
        st_obj.pyplot(
            build_oil_market_figure(
                market_prices,
                market_production,
                market_sources,
                market_rig_count,
            ),
            width="stretch",
            clear_figure=True,
        )
        render_chart_download(
            st_obj,
            market_download,
            title="原油价格、产量与钻机数",
            key="analysis.uae.oil.market.download",
        )
    with columns[1]:
        st_obj.pyplot(
            build_oil_revenue_figure(
                revenue_download,
                revenue_sources,
            ),
            width="stretch",
            clear_figure=True,
        )
        render_chart_download(
            st_obj,
            revenue_download,
            title="估算石油收入",
            key="analysis.uae.oil.revenue.download",
        )


def render_oil_fiscal_panel(st_obj: Any = st) -> dict[str, Any]:
    """用真实油价和产量估算石油收入，不生成占位渠道。"""

    st_obj.subheader("石油生产与收入")
    payload = _source_payload()
    if payload is None:
        message = "当前工作簿不可用，无法读取真实油价与原油产量。"
        st_obj.info(message)
        return {"status": "no_data", "message": message}

    try:
        content, file_name = payload
        with st_obj.spinner("正在读取日度油价与月度原油产量..."):
            data = _load_oil_market_cached(content, file_name)
        _render_oil_metrics(st_obj, data)
        revenue = estimate_monthly_oil_revenue(data.prices, data.production)
        st_obj.markdown("#### 估算石油收入")
        _render_revenue_metrics(st_obj, revenue)
        _render_charts(st_obj, data, revenue)
        with st_obj.expander("估算口径与限制", expanded=False):
            st_obj.markdown(
                "月度收入统一由布伦特原油现货月均价、原油日产量与"
                "当月天数估算，"
                "不等同于政府财政收入或国有企业现金流。"
            )
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.error(f"油价与产量数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {"status": "success", "source": file_name}


__all__ = ["render_oil_fiscal_panel"]
