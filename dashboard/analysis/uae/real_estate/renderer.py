"""Streamlit section for DLD Dubai real-estate monthly sales (期房/现房)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.real_estate.charts import (
    AMOUNT_LABEL,
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
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

REAL_ESTATE_EXPLANATION = """
- **期房 / 现房**：DLD 官方口径 Off-Plan（期房）与 Existing（现房）；现房含一手现房与
  二手房，官方数据无买卖双方身份字段，无法拆分一、二手。
- **笔数与金额**：均为迪拜全市场住宅 + 商业合计；金额单位为亿迪拉姆（AED，
  由工作簿百万 AED 口径折算，÷100）。
- **窗口**：最新**已结束**月份（若工作簿最新月恰为当前自然月、尚未过完，则回退
  一个月）往前 36 个月，不含当月滚动统计。
- **数据来源**：Dubai Land Department（迪拜土地局），月度_DLD sheet。
- 图中红色虚线为 2026 年 3 月美伊战争起始基准线。
""".strip()


@st.cache_data(show_spinner=False)
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


def _render_sales_chart(
    st_obj: Any,
    data: RealEstateData,
    last_month: pd.Period,
    *,
    market: str,
) -> None:
    title = DEFAULT_TITLES[market]
    count_column, amount_column = _market_columns(market)
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
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
        left, right = st_obj.columns(2, gap="small")
        try:
            _render_sales_chart(left, data, last_month, market="期房")
        except (KeyError, TypeError, ValueError) as exc:
            left.warning(f"期房销售图未加载：{exc}")
        try:
            _render_sales_chart(right, data, last_month, market="现房")
        except (KeyError, TypeError, ValueError) as exc:
            right.warning(f"现房销售图未加载：{exc}")
        with st_obj.expander("指标算法与解读", expanded=False):
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
