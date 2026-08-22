"""Streamlit section for 交通物流月度监测（UAE 港口 + 霍尔木兹 + 航空货运）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.transport.charts import (
    DUBAI_AIR_CARGO_TITLE,
    HORMUZ_CALLS_TITLE,
    UAE_PORT_VOLUME_TITLE,
    US_UAE_AIR_TITLE,
    build_dual_axis_figure,
    build_multi_series_figure,
)
from dashboard.analysis.uae.transport.data import (
    DUBAI_AIR_EXPORT_AWBS,
    DUBAI_AIR_EXPORT_TOTAL,
    DUBAI_AIR_IMPORT_AWBS,
    DUBAI_AIR_IMPORT_TOTAL,
    DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY,
    DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY,
    DOTT100_ERROR_KEY,
    HORMUZ_TOTAL_CALLS,
    HORMUZ_TANKER_CALLS,
    UAE_PORT_EXPORT_TOTAL,
    UAE_PORT_IMPORT_TOTAL,
    UAE_PORT_TANKER_EXPORT,
    UAE_PORT_TANKER_IMPORT,
    US_UAE_AIR_FREIGHT,
    US_UAE_AIR_PASSENGERS,
    TransportData,
    anchor_last_month,
    load_transport_data,
)
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

PORT_VOLUME_DISPLAY_SCALE = 1_000_000
TRANSPORT_DATA_SCHEMA_VERSION = "2026-08-22-dott100-v2-no-mail-compact-axis"

TRANSPORT_EXPLANATION = """
- **数据来源**：IMF PortWatch、Dubai Customs Airway Bill Details 和 US DOT BTS
  T-100；数据分别来自工作簿中的「月度_PortWatch」「月度_迪拜海关航空」和
  「月度_DOTT100」sheet。
- **指标口径**：左图为 UAE 港口进口/出口总量及其中油轮货量（百万吨，原始口径为吨）；
  右图为霍尔木兹过境总次数及油轮过境次数（艘次）；下方左图为迪拜航空货运运单数和总量，
  下方右图为美国↔阿联酋航空旅客与货运。
- **战争基准线**：红色虚线为 2026 年 3 月美伊战争起始；实证显示当月霍尔木兹
  油轮容量环比 -98%、UAE 港口到港 -77%，此后数月低位缓升。
- **窗口**：最新**已结束**月份（若工作簿最新月恰为当前自然月、尚未过完则回退
  一个月）往前 36 个月，不含当月滚动统计。
- **解读**：左图看 UAE 港口进出口货量结构，右图看霍尔木兹通道过境活动，
  下方左图同时看迪拜航空货运运单数与总量，下方右图看美国↔阿联酋航空旅客与货运。
""".strip()


@st.cache_data(show_spinner=False)
def _load_transport_cached(
    content: bytes,
    file_name: str,
    schema_version: str = TRANSPORT_DATA_SCHEMA_VERSION,
) -> TransportData:
    """读取交通物流数据；版本号用于淘汰旧字段结构缓存。"""

    del schema_version
    return load_transport_data(content, file_name=file_name)


def _render_chart(
    st_obj: Any,
    data: TransportData,
    last_month: pd.Period,
    *,
    title: str,
    figure_builder,
    download_columns: tuple[str, ...],
    chart_values: pd.DataFrame,
    download_values: pd.DataFrame | None = None,
    units: Mapping[str, str | None] | None = None,
    builder_kwargs: Mapping[str, Any] | None = None,
) -> None:
    source_text = "、".join(
        dict.fromkeys(
            data.metadata[column].source
            for column in download_columns
            if column in data.metadata
        )
    )
    if not source_text:
        source_text = "工作簿指标"
    figure_kwargs: dict[str, Any] = {
        "source_text": source_text,
        "last_month": last_month,
    }
    if builder_kwargs is None:
        figure_kwargs["units"] = units
    else:
        figure_kwargs.update(builder_kwargs)
    render_pyplot_figure(
        st_obj,
        figure_builder(chart_values, **figure_kwargs),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    render_chart_download(
        st_obj,
        (download_values if download_values is not None else chart_values)[
            list(download_columns)
        ].dropna(how="all"),
        title=title,
        key=f"analysis.uae.transport.{download_columns[0]}.download",
    )


def render_transport_section(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> dict[str, Any]:
    """渲染「交通物流」板块的两张海运图和两张航空运输图。"""

    st_obj.divider()
    st_obj.subheader("交通物流")
    try:
        with st_obj.spinner("正在读取交通物流数据..."):
            data = _load_transport_cached(
                content,
                file_name,
                schema_version=TRANSPORT_DATA_SCHEMA_VERSION,
            )
        last_month = anchor_last_month(data.values)
        left, right = st_obj.columns(2, gap="small")
        port_volume_columns = (
            UAE_PORT_IMPORT_TOTAL,
            UAE_PORT_EXPORT_TOTAL,
            UAE_PORT_TANKER_IMPORT,
            UAE_PORT_TANKER_EXPORT,
        )
        port_volume_display = data.values.astype(float).copy()
        port_volume_display.loc[:, list(port_volume_columns)] = (
            port_volume_display.loc[:, list(port_volume_columns)]
            / PORT_VOLUME_DISPLAY_SCALE
        )
        chart_rows = (
            (
                left,
                UAE_PORT_VOLUME_TITLE,
                port_volume_columns,
                "百万吨",
                port_volume_display,
                data.values,
            ),
            (
                right,
                HORMUZ_CALLS_TITLE,
                (HORMUZ_TOTAL_CALLS, HORMUZ_TANKER_CALLS),
                "艘次",
                data.values,
                data.values,
            ),
        )
        for cell, title, columns, unit, chart_values, download_values in chart_rows:
            try:
                _render_chart(
                    cell,
                    data,
                    last_month,
                    title=title,
                    figure_builder=build_multi_series_figure,
                    download_columns=columns,
                    chart_values=chart_values,
                    download_values=download_values,
                    builder_kwargs={
                        "columns": columns,
                        "title": title,
                        "unit": unit,
                        "legend_labels": (
                            ("霍尔木兹邮轮过境总次数", "霍尔木兹油轮过境次数")
                            if title == HORMUZ_CALLS_TITLE
                            else None
                        ),
                    },
                )
            except (KeyError, TypeError, ValueError) as exc:
                cell.warning(f"{title}未加载：{exc}")

        row_columns = st_obj.columns(2, gap="small")
        chart_specs = (
            (
                row_columns[0],
                DUBAI_AIR_CARGO_TITLE,
                (
                    DUBAI_AIR_IMPORT_AWBS,
                    DUBAI_AIR_EXPORT_AWBS,
                    DUBAI_AIR_IMPORT_TOTAL,
                    DUBAI_AIR_EXPORT_TOTAL,
                ),
                (DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY, DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY),
                {
                    "left_columns": (
                        DUBAI_AIR_IMPORT_AWBS,
                        DUBAI_AIR_EXPORT_AWBS,
                    ),
                    "right_columns": (
                        DUBAI_AIR_IMPORT_TOTAL,
                        DUBAI_AIR_EXPORT_TOTAL,
                    ),
                    "units": {
                        DUBAI_AIR_IMPORT_AWBS: "张",
                        DUBAI_AIR_EXPORT_AWBS: "张",
                        DUBAI_AIR_IMPORT_TOTAL: "吨",
                        DUBAI_AIR_EXPORT_TOTAL: "吨",
                    },
                    "legend_labels": (
                        DUBAI_AIR_IMPORT_AWBS,
                        DUBAI_AIR_EXPORT_AWBS,
                        DUBAI_AIR_IMPORT_TOTAL,
                        DUBAI_AIR_EXPORT_TOTAL,
                    ),
                },
            ),
            (
                row_columns[1],
                US_UAE_AIR_TITLE,
                (US_UAE_AIR_PASSENGERS, US_UAE_AIR_FREIGHT),
                (DOTT100_ERROR_KEY,),
                {
                    "left_columns": (US_UAE_AIR_PASSENGERS,),
                    "right_columns": (US_UAE_AIR_FREIGHT,),
                    "units": {
                        US_UAE_AIR_PASSENGERS: "人次",
                        US_UAE_AIR_FREIGHT: "磅",
                    },
                    "legend_labels": (
                        US_UAE_AIR_PASSENGERS,
                        US_UAE_AIR_FREIGHT,
                    ),
                },
            ),
        )
        for cell, title, columns, error_keys, builder_kwargs in chart_specs:
            try:
                errors = [data.load_errors[key] for key in error_keys if key in data.load_errors]
                if errors:
                    raise ValueError("；".join(errors))
                _render_chart(
                    cell,
                    data,
                    last_month,
                    title=title,
                    figure_builder=build_dual_axis_figure,
                    download_columns=columns,
                    chart_values=data.monthly_values,
                    builder_kwargs={
                        "columns": columns,
                        "title": title,
                        **builder_kwargs,
                    },
                )
            except (KeyError, TypeError, ValueError) as exc:
                cell.warning(f"{title}未加载：{exc}")
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
