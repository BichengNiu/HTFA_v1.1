"""阿联酋石油市场与财政收入监测面板。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.oil.alignment import (
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
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

OIL_FISCAL_EXPLANATION = """
- **油价**：布伦特期货/现货取自「日度_Wind」sheet（美元/桶，日/周度源序列）；
  指标卡取最新值与 **30 日前**对比的变化率。
- **原油产量**：月度平均桶/天；指标卡为最新月**环比**变化；图中为最近 36 个月，左轴万桶/天柱。
- **活跃钻机数**：贝克休斯月度活跃钻机数（台），环比变化；数据缺失时显示「—」。
- **收入估算**：`月度石油收入(亿美元) = 布伦特现货月均价(美元/桶) × 月均产量(桶/天) × 当月天数 ÷ 1亿`；
  价格或产量缺失的月份不生成收入，也不跨月填充。
- **同比与累计**：月度同比 = 对上年同月收入的变动率；本年度累计收入 = 年内逐月累加；
  年度累计同比 = 对上年同期累计值。
- **价格/产量拉动率**：按中点法把收入同比分解为价格拉动与产量拉动
  `(ΔP·V̄ + ΔV·P̄) ÷ (P₋₁₂·V₋₁₂)`，其中 `P̄=(P+P₋₁₂)/2`、`V̄=(V+V₋₁₂)/2`，
  两者之和恰好等于收入同比，用于判断收入变动主要来自价格还是产量。
- **解读**：收入先区分价格驱动还是产量驱动；产量受 OPEC+ 配额约束，价格受全球供需与地缘事件影响。
- 图中红色虚线为 2026 年 3 月美伊战争起始基准线。
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
    columns = st_obj.columns(4)
    price_names = ("布伦特期货", "布伦特现货")
    for column, name in zip(columns[:2], price_names):
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
    with columns[2]:
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

    if data.rig_count is None or data.rig_count.dropna().empty:
        with columns[3]:
            st_obj.metric("阿联酋石油活跃钻机数", "—")
        return

    value, as_of, change = _latest_change(data.rig_count)
    metadata = data.metadata[data.rig_count.name]
    with columns[3]:
        st_obj.metric(
            "阿联酋石油活跃钻机数",
            f"{value:,.0f} 台",
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
        value = latest[YOY_COLUMN]
        st_obj.metric("月度同比", f"{value:+.1f}%" if pd.notna(value) else "—")
    with columns[3]:
        value = latest[YTD_YOY_COLUMN]
        st_obj.metric(
            "年度累计同比",
            f"{value:+.1f}%" if pd.notna(value) else "—",
        )


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
            title="原油产量及活动钻机数",
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
        _render_revenue_metrics(st_obj, revenue)
        _render_charts(st_obj, data, revenue)
        with st_obj.expander("指标算法与解读", expanded=False):
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
        "government_finance": government_finance,
        "real_estate": real_estate,
        "transport": transport,
    }


__all__ = ["render_oil_fiscal_panel"]
