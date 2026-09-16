"""阿联酋石油市场与财政收入监测面板。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from htfa.monitoring.uae.downloads import render_chart_download
from htfa.monitoring.uae.periods import (
    common_latest_month,
    through_last_complete_month,
    within_month_window,
)
from htfa.monitoring.uae.oil.charts import (
    MARKET_PRODUCTION_LABEL,
    MARKET_RIG_COUNT_LABEL,
    DUBAI_PRICE_LABEL,
    REVENUE_LABEL,
    REVENUE_PRICE_LABEL,
    build_oil_market_figure,
    build_oil_price_figure,
    build_oil_production_figure,
    build_oil_revenue_figure,
    build_oil_revenue_only_figure,
    build_oil_rig_count_figure,
    build_war_pressure_index_figure,
    build_war_pressure_raw_figure,
)
from htfa.monitoring.uae.oil.data import (
    DUBAI_PRICE_INDICATOR,
    OilMarketData,
    load_oil_market_data,
)
from htfa.monitoring.uae.oil.revenue import (
    PRICE_BENCHMARK_COLUMN,
    PRICE_COLUMN,
    REVENUE_PRICE_BENCHMARK,
    REVENUE_COLUMN,
    YOY_COLUMN,
    YTD_COLUMN,
    YTD_YOY_COLUMN,
    estimate_monthly_oil_revenue,
)
from htfa.monitoring.uae.oil.war_pressure import (
    BALLISTIC_LABEL,
    CRUISE_LABEL,
    PRESSURE_LABEL,
    RAW_LABELS,
    UAV_LABEL,
    WarPressureData,
    load_war_pressure_data,
)
from htfa.monitoring.uae.plot_helpers import translate_source_text
from htfa.monitoring.uae.metrics import (
    format_count_value,
    format_scaled_value,
)
from htfa.ui_shared.chart_legend import render_pyplot_figure

OIL_FISCAL_EXPLANATION = """
- **油价**：布伦特原油现货价日度数据由美国能源信息署（EIA）发布，迪拜原油价格月度数据由国际货币基金组织初级商品价格系统发布，原始数据单位均为美元/桶。
- **原油产量**：由欧佩克月度石油市场报告（MOMR）发布，单位为桶/天，反映原油生产规模。
- **活跃钻机数**：由贝克休斯发布；原始数据按月份、地区及陆上/海上拆分，汇总为阿联酋月度活跃钻机数（台），反映石油勘探开发活动。
- **月度石油收入（估算）**：由布伦特原油现货价与欧佩克月度石油市场报告的阿联酋原油产量计算，价格按自然月取月均值后按`价格 × 产量 × 当月天数 ÷ 1亿` 计算（亿美元）。
""".strip()

WAR_PRESSURE_EXPLANATION = """
- **原始数据**：原始数据为日度弹道导弹、巡航导弹和无人机数量；月度武器数量为各日数量按月求和，反映公开登记的袭击活动。
- **战争压力指数**：原始数据为上述日度数量；按 `9×log1p(弹道导弹数量)+3×log1p(巡航导弹数量)+log1p(无人机数量)` 加权后按月求和，
  再在战争观测窗口内做 min-max 归一化 `100×(当月值−最小值)÷(最大值−最小值)`。
  `log1p(x)=ln(1+x)` 用于压缩极端值；指数越高表示登记袭击强度相对越高，最高月为100、最低月为0。
""".strip()


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


def _complete_war_pressure_values(data: WarPressureData) -> pd.DataFrame:
    """删除 WAM 中观测天数不足一个自然月的月度行。"""

    values = data.values.loc[:, [*RAW_LABELS, PRESSURE_LABEL]].sort_index()
    if data.observation_days is None:
        return values
    days = data.observation_days.reindex(values.index)
    required_days = pd.PeriodIndex(values.index, freq="M").days_in_month
    complete = days.ge(required_days).fillna(False)
    return values.loc[complete]


def _monthly_mean_series(series: pd.Series) -> pd.Series:
    """将价格序列按自然月取均值，并将索引规范为月末。"""

    clean = through_last_complete_month(series.dropna().sort_index())
    if clean.empty:
        return clean
    periods = pd.DatetimeIndex(clean.index).to_period("M")
    monthly = clean.groupby(periods).mean()
    monthly.index = monthly.index.to_timestamp(how="end").normalize()
    monthly.index.name = "月份"
    return monthly


def _render_oil_metrics(st_obj: Any, data: OilMarketData) -> None:
    columns = st_obj.columns(4)
    price_names = tuple(
        name
        for name in ("布伦特期货", "布伦特现货")
        if name in data.prices.columns
    )
    for column, name in zip(columns[:2], price_names):
        price_series = through_last_complete_month(data.prices[name])
        if price_series.empty:
            continue
        value, as_of, change = _latest_change(price_series, days=30)
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
    production_column = columns[len(price_names)]
    with production_column:
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
        with columns[len(price_names) + 1]:
            st_obj.metric("阿联酋石油活跃钻机数", "—")
        return

    value, as_of, change = _latest_change(data.rig_count)
    metadata = data.metadata[data.rig_count.name]
    with columns[len(price_names) + 1]:
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

    latest_values = _complete_war_pressure_values(data).dropna(
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
    values = _complete_war_pressure_values(data)
    if values.empty:
        st_obj.info("战争压力数据没有完整自然月，暂不绘图。")
        return
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


def _render_legacy_combined_charts(
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


def _render_charts(
    st_obj: Any,
    data: OilMarketData,
    revenue: pd.DataFrame,
) -> None:
    """Render the oil charts in the requested two-by-two layout."""

    production_source = data.metadata[data.production.name].source
    rig_count_source = (
        None
        if data.rig_count is None
        else data.metadata[data.rig_count.name].source
    )
    price_source = data.metadata[REVENUE_PRICE_BENCHMARK].source
    dubai_price = None
    dubai_metadata = data.metadata.get(DUBAI_PRICE_INDICATOR[0])
    if DUBAI_PRICE_INDICATOR[0] in data.prices.columns:
        dubai_price = _monthly_mean_series(
            data.prices[DUBAI_PRICE_INDICATOR[0]]
        ).rename(DUBAI_PRICE_LABEL)
    price_sources = [price_source]
    if dubai_price is not None and not dubai_price.empty and dubai_metadata:
        price_sources.append(dubai_metadata.source)
    price_source_text = "、".join(dict.fromkeys(price_sources))
    revenue_sources = "、".join(
        dict.fromkeys((price_source, production_source))
    )

    production_last_month = common_latest_month(
        [(data.production.name, data.production)]
    )
    production = within_month_window(
        data.production,
        first_month=production_last_month - 36,
        last_month=production_last_month,
    ).div(10_000).rename(MARKET_PRODUCTION_LABEL)
    if data.rig_count is None or data.rig_count.dropna().empty:
        rigs = None
    else:
        rig_last_month = common_latest_month(
            [(data.rig_count.name, data.rig_count)]
        )
        rigs = within_month_window(
            data.rig_count,
            first_month=rig_last_month - 36,
            last_month=rig_last_month,
        ).rename(MARKET_RIG_COUNT_LABEL)

    price_cutoff_series = [(REVENUE_COLUMN, revenue[REVENUE_COLUMN])]
    if dubai_price is not None and not dubai_price.empty:
        price_cutoff_series.append((DUBAI_PRICE_LABEL, dubai_price))
    revenue_last_month = common_latest_month(price_cutoff_series)
    revenue_window = within_month_window(
        revenue,
        first_month=revenue_last_month - 36,
        last_month=revenue_last_month,
    )
    price_download = revenue_window[[PRICE_COLUMN]].rename(
        columns={PRICE_COLUMN: REVENUE_PRICE_LABEL}
    )
    dubai_window = None
    if dubai_price is not None and not dubai_price.empty:
        dubai_window = within_month_window(
            dubai_price,
            first_month=revenue_last_month - 36,
            last_month=revenue_last_month,
        )
        price_download = price_download.join(dubai_window, how="outer").sort_index()
    revenue_download = revenue_window[[REVENUE_COLUMN]]

    first_row = st_obj.columns(2, gap="small")
    second_row = st_obj.columns(2, gap="small")
    with first_row[0]:
        render_pyplot_figure(
            st_obj,
            build_oil_production_figure(
                production,
                production_source,
                units={MARKET_PRODUCTION_LABEL: "万桶/天"},
            ),
            bbox_inches=None,
            place_legend_bottom=False,
        )
        render_chart_download(
            st_obj,
            production,
            title="原油产量",
            key="analysis.uae.oil.production.download",
        )
    with first_row[1]:
        if rigs is None or rigs.dropna().empty:
            st_obj.info("活动钻井机数暂无有效观测。")
        else:
            render_pyplot_figure(
                st_obj,
                build_oil_rig_count_figure(
                    rigs,
                    rig_count_source or "",
                    units={MARKET_RIG_COUNT_LABEL: data.metadata[
                        data.rig_count.name
                    ].unit},
                ),
                bbox_inches=None,
                place_legend_bottom=False,
            )
            render_chart_download(
                st_obj,
                rigs,
                title="活动钻井机数",
                key="analysis.uae.oil.rig_count.download",
            )
    with second_row[0]:
        render_pyplot_figure(
            st_obj,
            build_oil_price_figure(
                revenue_window,
                price_source_text,
                units={REVENUE_PRICE_LABEL: data.metadata[
                    REVENUE_PRICE_BENCHMARK
                ].unit, DUBAI_PRICE_LABEL: "美元/桶"},
                dubai_price=dubai_window,
            ),
            bbox_inches=None,
            place_legend_bottom=False,
        )
        render_chart_download(
            st_obj,
            price_download,
            title="石油价格",
            key="analysis.uae.oil.price.download",
        )
    with second_row[1]:
        render_pyplot_figure(
            st_obj,
            build_oil_revenue_only_figure(
                revenue_window,
                revenue_sources,
                units={REVENUE_LABEL: "亿美元"},
            ),
            bbox_inches=None,
            place_legend_bottom=False,
        )
        render_chart_download(
            st_obj,
            revenue_download,
            title="石油收入",
            key="analysis.uae.oil.revenue.download",
        )


def render_oil_fiscal_panel(
    st_obj: Any,
    payload: tuple[bytes, str],
) -> dict[str, Any]:
    """用显式工作簿载荷估算石油收入，不生成占位渠道。"""

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
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.error(f"油价与产量数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {
        "status": "success",
        "source": file_name,
        "war_pressure": war_pressure_available,
    }


__all__ = ["render_oil_fiscal_panel"]
