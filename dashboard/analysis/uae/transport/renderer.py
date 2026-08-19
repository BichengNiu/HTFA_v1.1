"""Streamlit section for IMF PortWatch 交通物流月度监测（霍尔木兹 + UAE 港口）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.transport.charts import (
    HORMUZ_CHANNEL_TITLE,
    HORMUZ_CALLS_LABEL,
    HORMUZ_CAPACITY_LABEL,
    HORMUZ_TANKER_CAPACITY_LABEL,
    PORT_LINKAGE_TITLE,
    UAE_CALLS_LABEL,
    build_hormuz_channel_figure,
    build_port_linkage_figure,
)
from dashboard.analysis.uae.transport.data import (
    HORMUZ_TANKER_CALLS,
    UAE_PORT_CALLS,
    TransportData,
    anchor_last_month,
    load_transport_data,
)
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

TRANSPORT_EXPLANATION = """
- **数据来源**：IMF PortWatch 日度海运数据（每月聚合自「月度_PortWatch」sheet，
  该 sheet 由 uae.duckdb 按月汇总生成）。
- **指标口径**：霍尔木兹油轮/总载货容量为月度过境货量（吨，图中折为百万吨）；
  霍尔木兹油轮过境与 UAE 港口总到港为月度艘次。UAE 到港为全国 15 个港口合计。
- **战争基准线**：红色虚线为 2026 年 3 月美伊战争起始；实证显示当月霍尔木兹
  油轮容量环比 -98%、UAE 港口到港 -77%，此后数月低位缓升。
- **窗口**：最新**已结束**月份（若工作簿最新月恰为当前自然月、尚未过完则回退
  一个月）往前 36 个月，不含当月滚动统计。
- **解读**：图1 看通道本身（封锁/禁航先打在油轮吨位上）；图2 看外因→内果
  （通道流量收缩如何传导到 UAE 本国港口活动）。
""".strip()


@st.cache_data(show_spinner=False)
def _load_transport_cached(
    content: bytes,
    file_name: str,
) -> TransportData:
    return load_transport_data(content, file_name=file_name)


def _render_chart(
    st_obj: Any,
    data: TransportData,
    last_month: pd.Period,
    *,
    title: str,
    figure_builder,
    download_columns: tuple[str, ...],
    units: Mapping[str, str | None] | None = None,
) -> None:
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    render_pyplot_figure(
        st_obj,
        figure_builder(
            data.values,
            source_text=source_text,
            last_month=last_month,
            units=units,
        ),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    render_chart_download(
        st_obj,
        data.values[list(download_columns)].dropna(how="all"),
        title=title,
        key=f"analysis.uae.transport.{download_columns[0]}.download",
    )


def render_transport_section(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> dict[str, Any]:
    """渲染「交通物流」板块：霍尔木兹通道 + UAE 港口联动 两张双轴图。"""

    st_obj.divider()
    st_obj.subheader("交通物流")
    try:
        with st_obj.spinner("正在读取 PortWatch 海运数据..."):
            data = _load_transport_cached(content, file_name)
        last_month = anchor_last_month(data.values)
        left, right = st_obj.columns(2, gap="small")
        try:
            _render_chart(
                left,
                data,
                last_month,
                title=HORMUZ_CHANNEL_TITLE,
                figure_builder=build_hormuz_channel_figure,
                download_columns=("霍尔木兹油轮过境", "霍尔木兹总容量", "霍尔木兹油轮容量"),
                units={
                    HORMUZ_CALLS_LABEL: data.metadata[HORMUZ_TANKER_CALLS].unit,
                    HORMUZ_CAPACITY_LABEL: "百万吨",
                    HORMUZ_TANKER_CAPACITY_LABEL: "百万吨",
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            left.warning(f"霍尔木兹通道图未加载：{exc}")
        try:
            _render_chart(
                right,
                data,
                last_month,
                title=PORT_LINKAGE_TITLE,
                figure_builder=build_port_linkage_figure,
                download_columns=("UAE港口总到港", "霍尔木兹油轮容量"),
                units={
                    UAE_CALLS_LABEL: data.metadata[UAE_PORT_CALLS].unit,
                    HORMUZ_TANKER_CAPACITY_LABEL: "百万吨",
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            right.warning(f"港口联动图未加载：{exc}")
        with st_obj.expander("指标算法与解读", expanded=False):
            st_obj.markdown(TRANSPORT_EXPLANATION)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        st_obj.error(f"交通物流数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {
        "status": "success",
        "source": file_name,
        "as_of": last_month.strftime("%Y-%m"),
    }


__all__ = ["TRANSPORT_EXPLANATION", "render_transport_section"]
