"""Streamlit section for DLD Dubai real-estate monthly sales (期房/现房)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from htfa.monitoring.uae.downloads import render_chart_download
from htfa.monitoring.uae.real_estate.charts import (
    AMOUNT_LABEL,
    AMOUNT_UNIT_FACTOR,
    COUNT_LABEL,
    DEFAULT_TITLES,
    SALES_CONFIG,
    build_sales_figure,
    sales_display_values,
)
from htfa.monitoring.uae.real_estate.data import (
    OFFPLAN_AMOUNT,
    OFFPLAN_COUNT,
    READY_AMOUNT,
    READY_COUNT,
    RealEstateData,
    anchor_last_month,
    load_real_estate_data,
)
from htfa.monitoring.uae.metrics import (
    _source_note_from_metadata,
    format_count_value,
    format_currency_value,
    latest_month_value,
    month_and_year_delta_text,
    render_metric_cards,
    source_text_from_metadata,
)
from htfa.ui_shared.chart_legend import render_pyplot_figure
from htfa.monitoring.uae.supplemental_data import PROPERTY_CHARTS
from htfa.monitoring.uae.supplemental_renderer import render_supplemental_charts

REAL_ESTATE_EXPLANATION = """
- **交易类型**：由迪拜土地局发布；原始数据为房地产交易明细，按登记月份、交易类型（期房/现房）及市场（住宅/商业）聚合为月度指标；现房含一手和二手房。
- **笔数与金额**：原始数据为交易笔数和金额；笔数反映交易数量，金额原始单位为百万 AED。两类指标分别反映房地产交易活跃度和成交规模。
- **确认新期房项目数（左轴）**：最近 28 天确认入市的新项目数。新项目首次成交后的 28 天内至少成交 10 笔，才算通过确认。
- **活跃期房项目数（右轴）**：最近 28 天至少成交 3 笔的项目数，包括新项目和老项目。
- **月均值**：每周统计一次上述数量，再取当月平均值，因此可能出现小数。两个指标可能包含同一项目，不能相加。
""".strip()


@st.cache_data(show_spinner=False, max_entries=4)
def _load_real_estate_cached(
    content: Any,
    file_name: str,
) -> RealEstateData:
    return load_real_estate_data(content, file_name=file_name)


def _market_columns(market: str) -> tuple[str, str]:
    try:
        return SALES_CONFIG[market]
    except KeyError as exc:
        raise ValueError(f"未知房地产口径：{market}") from exc


def _format_real_estate_value(
    value: float | None,
    *,
    unit: str,
    scale: float = 1.0,
) -> str | None:
    if scale != 1:
        return format_currency_value(
            value,
            "迪拉姆",
            input_scale=1_000_000,
        )
    return format_count_value(value, unit)


def _render_real_estate_metrics(
    st_obj: Any,
    data: RealEstateData,
    last_month: pd.Period,
) -> None:
    """渲染房地产板块四个最新完整月指标卡。"""

    values = data.values.loc[
        pd.PeriodIndex(data.values.index, freq="M") <= last_month
    ]
    cards = []
    for label, column, unit, scale in (
        ("现房销售笔数", READY_COUNT, "笔", 1.0),
        ("现房销售金额", READY_AMOUNT, "亿迪拉姆", AMOUNT_UNIT_FACTOR),
        ("期房销售笔数", OFFPLAN_COUNT, "笔", 1.0),
        ("期房销售金额", OFFPLAN_AMOUNT, "亿迪拉姆", AMOUNT_UNIT_FACTOR),
    ):
        series = values[column]
        value, as_of = latest_month_value(series)
        cards.append(
            (
                label,
                _format_real_estate_value(value, unit=unit, scale=scale),
                month_and_year_delta_text(series),
                _source_note_from_metadata(data.metadata, column, as_of),
            )
        )
    render_metric_cards(st_obj, cards)


def _render_sales_chart(
    st_obj: Any,
    data: RealEstateData,
    last_month: pd.Period,
    *,
    market: str,
) -> None:
    title = DEFAULT_TITLES[market]
    count_column, amount_column = _market_columns(market)
    chart_values = data.values
    chart_metadata = data.metadata
    if count_column not in chart_values.columns:
        if data.raw_values is None:
            raise ValueError(f"{market}明细数据不可用")
        chart_values = data.raw_values
        chart_metadata = data.raw_metadata or {}
    count_metadata = chart_metadata.get(count_column)
    source_text = source_text_from_metadata(chart_metadata)
    render_pyplot_figure(
        st_obj,
        build_sales_figure(
            chart_values,
            market=market,
            title=title,
            source_text=source_text,
            last_month=last_month,
            units={
                COUNT_LABEL: count_metadata.unit if count_metadata else "笔",
                AMOUNT_LABEL: "亿迪拉姆",
            },
        ),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    chart_frame = sales_display_values(
        chart_values,
        last_month=last_month,
    )[[count_column, amount_column]].dropna(how="all")
    render_chart_download(
        st_obj,
        chart_frame,
        title=title,
        key=f"analysis.uae.real_estate.{market}.download",
    )


def render_real_estate_section(
    st_obj: Any,
    content: Any,
    file_name: str,
) -> dict[str, Any]:
    """渲染「房地产」板块：四张成交图和一张项目数量图。"""

    st_obj.divider()
    st_obj.subheader("房地产")
    try:
        with st_obj.spinner("正在读取 DLD 月度房地产销售数据..."):
            data = _load_real_estate_cached(content, file_name)
        last_month = anchor_last_month(data.values)
        try:
            _render_real_estate_metrics(st_obj, data, last_month)
        except (KeyError, TypeError, ValueError) as exc:
            st_obj.warning(f"房地产指标卡未加载：{exc}")
        for row_markets in (
            ("现房住宅", "期房住宅"),
            ("现房商业", "期房商业"),
        ):
            columns = st_obj.columns(2, gap="small")
            for column, market in zip(columns, row_markets, strict=True):
                try:
                    _render_sales_chart(column, data, last_month, market=market)
                except (KeyError, TypeError, ValueError) as exc:
                    column.warning(f"{market}销售图未加载：{exc}")
        render_supplemental_charts(st_obj, content, file_name, PROPERTY_CHARTS)
        with st_obj.expander("指标算法与解读", expanded=True, key="uae-indicator-explanation-property"):
            st_obj.markdown(REAL_ESTATE_EXPLANATION)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        st_obj.error(f"房地产数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {
        "status": "success",
        "source": file_name,
        "as_of": last_month.strftime("%Y-%m"),
    }


__all__ = ["REAL_ESTATE_EXPLANATION", "render_real_estate_section"]
