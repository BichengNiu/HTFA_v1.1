"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

from datetime import date

import streamlit as st

import htfa.monitoring.energy_supply.processing.catalogs as data_store
import htfa.monitoring.energy_supply.processing.csv_export as csv_export
import htfa.monitoring.energy_supply.processing.port_charts as port_charts
import htfa.monitoring.energy_supply.processing.portwatch as PORTWATCH
import htfa.monitoring.energy_supply.ui.dashboard_rows as dashboard_rows
from htfa.monitoring.energy_supply.processing.entity_names import display_name
from htfa.monitoring.energy_supply.processing.port_inventory import country_label
from htfa.monitoring.energy_supply.processing.port_types import port_type_label
from htfa.monitoring.energy_supply.ui.ui_controls import (
    ALL_SELECTION,
    multiselect_with_all,
    selected_values,
)
from htfa.monitoring.energy_supply.ui.widget_keys import energy_key

from . import cache, charts


def _port_chart_filters(ports: list[dict]) -> tuple[str, list[dict], str]:
    columns = st.columns([1.1, 1, 1, 1, 1.6, 1.8])
    with columns[0]:
        period = st.selectbox(
            "时间范围",
            port_charts.TIME_RANGES,
            index=4,
            key=energy_key("port_chart_period"),
        )
    with columns[1]:
        aggregation = st.selectbox(
            "聚合方式",
            list(port_charts.AGGREGATIONS),
            key=energy_key("port_chart_aggregation"),
        )
    names = {str(port["portid"]): display_name(port) for port in ports}
    filters = (
        ("国家", "country", lambda port: country_label(port.get("country")), None),
        ("水域", "region", lambda port: port.get("region") or "水域未知", None),
        ("港口类型", "type", port_type_label, None),
        ("港口", "port", lambda port: str(port["portid"]), names.get),
    )
    filtered = list(ports)
    for column, (label, suffix, value_of, formatter) in zip(columns[2:], filters):
        options = sorted({value_of(port) for port in filtered}, key=formatter or str)
        key = f"port_chart_filter_{suffix}"
        current = st.session_state.get(energy_key(key), [])
        # An upstream filter can remove all formerly selected choices. Reset
        # that downstream control, but preserve an intentionally empty choice.
        if (
            current
            and ALL_SELECTION not in current
            and not set(current).intersection(options)
        ):
            st.session_state[energy_key(key)] = [ALL_SELECTION]
        with column:
            selection = multiselect_with_all(
                label, options, key=key, format_func=formatter, all_label="全部"
            )
        selected = set(selected_values(selection, options))
        filtered = [port for port in filtered if value_of(port) in selected]
    return period, filtered, aggregation


def render_ports_panel(
    ports: list[dict], selected_day: date | None, port_error: str | None
) -> None:
    listed_ports = ports
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    metrics = dashboard_rows.port_metrics(ports, selected_day)
    for start in range(0, len(metrics), 4):
        for column, (label, value) in zip(st.columns(4), metrics[start : start + 4]):
            column.metric(label, value)
    if selected_day:
        period, chart_ports, aggregation = _port_chart_filters(ports)
        listed_ports = chart_ports
        port_ids = tuple(
            sorted(
                {
                    str(p["portid"])
                    for p in chart_ports
                    if PORTWATCH.has_independent_statistics(p)
                }
            )
        )
        path = data_store.database_path()
        history = cache.dashboard_data_port_time_series(
            port_ids, selected_day, (str(path), path.stat().st_mtime_ns)
        )
        if history:
            first = port_charts.window_start(selected_day, period, history[0]["date"])
            fields = [
                "date",
                "portcalls",
                *(f"portcalls_{kind}" for kind in PORTWATCH.SHIP_TYPES),
            ]
            rows = tuple(tuple(row[field] for field in fields) for row in history)
            images = charts.port_chart_images(rows, first, aggregation)
            series = list(port_charts.series_labels(aggregation).items())
            visible_history = port_charts.aggregate_rows(rows, first, aggregation)
            for start in (0, 3):
                for column, image, (field, title) in zip(
                    st.columns(3), images[start : start + 3], series[start : start + 3]
                ):
                    with column:
                        st.image(image, width="stretch")
                        st.download_button(
                            "下载数据",
                            data=csv_export.csv_bytes(
                                [
                                    {
                                        "日期": row["date"],
                                        **(
                                            {
                                                "期间开始": row["period_start"],
                                                "期间结束": row["period_end"],
                                            }
                                            if aggregation != "日度"
                                            else {}
                                        ),
                                        title: row[field],
                                    }
                                    for row in visible_history
                                ],
                                [
                                    "日期",
                                    *(
                                        ["期间开始", "期间结束"]
                                        if aggregation != "日度"
                                        else []
                                    ),
                                    title,
                                ],
                            ),
                            file_name=f"{title.replace('/', '_')}.csv",
                            mime="text/csv",
                            key=energy_key(f"port_chart_download_{field}"),
                            type="primary",
                            on_click="ignore",
                        )
        else:
            st.info(
                "所选港口暂无独立进港统计" if chart_ports else "没有符合筛选条件的港口"
            )
    port_rows = dashboard_rows.port_rows(listed_ports, selected_day)
    if port_rows:
        st.dataframe(
            port_rows,
            width="stretch",
            hide_index=True,
            height=560,
            column_config={
                "来源": st.column_config.LinkColumn("来源"),
                "港口类型": st.column_config.TextColumn("港口类型", width=180),
                "业务特点": st.column_config.TextColumn("业务特点", width=520),
                **{
                    name: st.column_config.NumberColumn(format="%d")
                    for name in port_rows[0]
                    if name.endswith("艘次")
                },
            },
        )
        st.download_button(
            "下载列表",
            csv_export.csv_bytes(port_rows, list(port_rows[0])),
            file_name=f"portwatch_ports_{selected_day.isoformat() if selected_day else 'unknown'}.csv",
            mime="text/csv",
            type="primary",
        )
