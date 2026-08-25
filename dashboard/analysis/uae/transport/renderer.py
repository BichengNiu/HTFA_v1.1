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
from dashboard.analysis.uae.metrics import (
    _source_note_from_metadata,
    format_count_value,
    format_scaled_value,
    latest_month_value,
    month_and_year_delta_text,
    render_metric_cards,
)
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

PORT_VOLUME_DISPLAY_SCALE = 1_000_000
TRANSPORT_DATA_SCHEMA_VERSION = "2026-08-22-dott100-v2-no-mail-compact-axis"

TRANSPORT_EXPLANATION = """
- **港口货量**：由国际货币基金组织港口监测发布；原始数据为日度各港口观测，按月汇总全 UAE 港口的进口、出口及油轮货量，
  原始单位吨，展示时换算为百万吨；反映港口货物流量及油运结构。
- **霍尔木兹过境**：由国际货币基金组织港口监测发布；原始数据为日度海峡观测，按月汇总船舶过境总次数和油轮过境次数（艘次），反映海峡航运活动。
- **迪拜航空货运**：由迪拜海关航空运单明细发布；原始数据为航空运单行项目，按创建日期归入月份汇总为进出口运单数（张）和货运量（吨），
  分别反映航空货运订单数量与实物吞吐量。
- **美国—阿联酋航空运输**：由美国交通部统计局 BTS T-100 国际航段发布；原始数据为承运商、机场对、机型及舱等层级的月度航段记录，按月份和方向汇总为双边旅客人次和货运磅数，
  反映两国航空客运与货运联系规模。
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


def _render_transport_metrics(
    st_obj: Any,
    data: TransportData,
    last_month: pd.Period,
) -> None:
    """渲染交通物流板块的海运与航空运输月度指标卡。"""

    values = data.values.loc[
        pd.PeriodIndex(data.values.index, freq="M") <= last_month
    ]

    def _card(
        label: str,
        series: pd.Series,
        *,
        unit: str,
        scale: float = 1.0,
        source_column: str,
    ) -> tuple[str, str | None, str | None, str]:
        value, as_of = latest_month_value(series)
        return (
            label,
            (
                format_scaled_value(value / scale, unit)
                if unit == "百万吨"
                else format_count_value(value, unit)
            ),
            month_and_year_delta_text(series),
            _source_note_from_metadata(data.metadata, source_column, as_of),
        )

    maritime_cards = []
    for label, column, unit, scale in (
        ("阿联酋港口进口量", UAE_PORT_IMPORT_TOTAL, "百万吨", PORT_VOLUME_DISPLAY_SCALE),
        ("阿联酋港口出口量", UAE_PORT_EXPORT_TOTAL, "百万吨", PORT_VOLUME_DISPLAY_SCALE),
        ("霍尔木兹过境总次数", HORMUZ_TOTAL_CALLS, "艘次", 1.0),
        ("霍尔木兹油轮过境次数", HORMUZ_TANKER_CALLS, "艘次", 1.0),
    ):
        maritime_cards.append(
            _card(
                label,
                values[column],
                unit=unit,
                scale=scale,
                source_column=column,
            )
        )

    render_metric_cards(st_obj, maritime_cards, n=4)

    air_values = data.monthly_values.loc[
        pd.PeriodIndex(data.monthly_values.index, freq="M") <= last_month
    ]

    def _sum_series(columns: tuple[str, ...], name: str) -> pd.Series:
        if any(column not in air_values.columns for column in columns):
            return pd.Series(dtype=float, name=name)
        return air_values.loc[:, list(columns)].sum(axis=1, min_count=len(columns)).rename(name)

    def _source_column(columns: tuple[str, ...]) -> str:
        return next(
            (column for column in columns if column in data.metadata),
            columns[0],
        )

    air_cards = [
        _card(
            "迪拜航空货运运单数",
            _sum_series(
                (DUBAI_AIR_IMPORT_AWBS, DUBAI_AIR_EXPORT_AWBS),
                "迪拜航空货运运单数",
            ),
            unit="张",
            source_column=_source_column(
                (DUBAI_AIR_IMPORT_AWBS, DUBAI_AIR_EXPORT_AWBS)
            ),
        ),
        _card(
            "迪拜航空货运总量",
            _sum_series(
                (DUBAI_AIR_IMPORT_TOTAL, DUBAI_AIR_EXPORT_TOTAL),
                "迪拜航空货运总量",
            ),
            unit="吨",
            source_column=_source_column(
                (DUBAI_AIR_IMPORT_TOTAL, DUBAI_AIR_EXPORT_TOTAL)
            ),
        ),
        _card(
            "美国—阿联酋航空旅客",
            _sum_series((US_UAE_AIR_PASSENGERS,), "美国—阿联酋航空旅客"),
            unit="人次",
            source_column=_source_column((US_UAE_AIR_PASSENGERS,)),
        ),
        _card(
            "美国—阿联酋航空货运",
            _sum_series((US_UAE_AIR_FREIGHT,), "美国—阿联酋航空货运"),
            unit="磅",
            source_column=_source_column((US_UAE_AIR_FREIGHT,)),
        ),
    ]
    st_obj.caption("航空运输")
    render_metric_cards(st_obj, air_cards, n=4)


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
        try:
            _render_transport_metrics(st_obj, data, last_month)
        except (KeyError, TypeError, ValueError) as exc:
            st_obj.warning(f"交通物流指标卡未加载：{exc}")
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
                            (
                                "霍尔木兹海峡过境总次数",
                                "霍尔木兹海峡油轮过境次数",
                            )
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
                        "迪拜航空货运进口运单数",
                        "迪拜航空货运出口运单数",
                        "迪拜航空货运进口总量",
                        "迪拜航空货运出口总量",
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
                        "美国—阿联酋航空旅客",
                        "美国—阿联酋航空货运",
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
        with st_obj.expander("指标算法与解读", expanded=True):
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
