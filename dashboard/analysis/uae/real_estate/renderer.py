"""Streamlit section for DLD Dubai real-estate monthly sales (期房/现房)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.real_estate.charts import (
    AMOUNT_LABEL,
    AMOUNT_UNIT_FACTOR,
    COUNT_LABEL,
    DEFAULT_TITLES,
    build_sales_figure,
    sales_display_values,
)
from dashboard.analysis.uae.real_estate.data import (
    OFFPLAN_AMOUNT,
    OFFPLAN_COUNT,
    READY_AMOUNT,
    READY_COUNT,
    RealEstateData,
    anchor_last_month,
    load_real_estate_data,
)
from dashboard.analysis.uae.metrics import (
    _source_note_from_metadata,
    format_count_value,
    format_currency_value,
    latest_month_value,
    month_and_year_delta_text,
    render_metric_cards,
    source_text_from_metadata,
)
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

REAL_ESTATE_EXPLANATION = """
- **交易类型**：由迪拜土地局发布；原始数据为房地产交易明细，按登记月份、交易类型（Off-Plan 期房/Existing 现房）及市场（住宅/商业）聚合为月度指标；现房含一手和二手，官方字段无法进一步拆分。
- **笔数与金额**：原始数据为交易笔数和金额；笔数反映交易数量，金额原始单位为百万 AED，除以100换算为亿迪拉姆后反映成交规模。
  两类指标分别反映房地产交易活跃度和成交规模。
""".strip()


def _load_real_estate_cached(
    content: bytes,
    file_name: str,
) -> RealEstateData:
    return load_real_estate_data(content, file_name=file_name)


def _market_columns(market: str) -> tuple[str, str]:
    if market == "期房":
        return OFFPLAN_COUNT, OFFPLAN_AMOUNT
    if market == "现房":
        return READY_COUNT, READY_AMOUNT
    raise ValueError(f"未知房地产市场：{market}")


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
    render_metric_cards(st_obj, cards, n=4)


def _render_sales_chart(
    st_obj: Any,
    data: RealEstateData,
    last_month: pd.Period,
    *,
    market: str,
) -> None:
    title = DEFAULT_TITLES[market]
    count_column, amount_column = _market_columns(market)
    source_text = source_text_from_metadata(data.metadata)
    render_pyplot_figure(
        st_obj,
        build_sales_figure(
            data.values,
            market=market,
            title=title,
            source_text=source_text,
            last_month=last_month,
            units={
                COUNT_LABEL: data.metadata[count_column].unit,
                AMOUNT_LABEL: "亿迪拉姆",
            },
        ),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    chart_frame = sales_display_values(
        data.values,
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
    content: bytes,
    file_name: str,
) -> dict[str, Any]:
    """渲染「房地产」板块：期房、现房 两张笔数+金额双轴图。"""

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
        left, right = st_obj.columns(2, gap="small")
        try:
            _render_sales_chart(left, data, last_month, market="现房")
        except (KeyError, TypeError, ValueError) as exc:
            left.warning(f"现房销售图未加载：{exc}")
        try:
            _render_sales_chart(right, data, last_month, market="期房")
        except (KeyError, TypeError, ValueError) as exc:
            right.warning(f"期房销售图未加载：{exc}")
        with st_obj.expander("指标算法与解读", expanded=True):
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
