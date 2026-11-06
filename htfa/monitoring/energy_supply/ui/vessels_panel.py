"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

import streamlit as st

import htfa.monitoring.energy_supply.processing.ais as AIS
import htfa.monitoring.energy_supply.processing.catalogs as data_store
import htfa.monitoring.energy_supply.processing.csv_export as csv_export
import htfa.monitoring.energy_supply.processing.port_charts as port_charts
import htfa.monitoring.energy_supply.processing.vessel_charts as vessel_charts
import htfa.monitoring.energy_supply.ui.dashboard_rows as dashboard_rows
from htfa.monitoring.energy_supply.contracts import DashboardViewState
from htfa.monitoring.energy_supply.ui.ui_controls import (
    ALL_SELECTION,
    multiselect_with_all,
    selected_values,
)
from htfa.monitoring.energy_supply.ui.widget_keys import energy_key

from . import cache, charts


def render_ais_panel(state: DashboardViewState) -> None:
    if state.archive_error:
        st.error(state.archive_error)
    if state.open_state.get("error"):
        st.error(f"Open Waters 快照错误：{state.open_state['error']}")
    if state.ais_status.get("last_error"):
        st.error(f"最近连接错误：{state.ais_status['last_error']}")
    cards = st.empty()
    columns = st.columns([1.1, 1, 1.6, 1.8])
    with columns[0]:
        period = st.selectbox(
            "时间范围",
            port_charts.TIME_RANGES,
            index=4,
            key=energy_key("vessel_chart_period"),
        )
    with columns[1]:
        aggregation = st.selectbox(
            "聚合方式",
            list(port_charts.AGGREGATIONS),
            key=energy_key("vessel_chart_aggregation"),
        )
    last = state.snapshot_day or AIS.utc_now().date()
    path = data_store.database_path()
    identity = (str(path), path.stat().st_mtime_ns)
    history = cache.vessel_charts_history(last, identity)
    earliest = min(
        (AIS.parse_utc(r["observed_at"]).date() for r in history), default=last
    )
    first = port_charts.window_start(last, period, earliest)
    visible = [
        r
        for r in history
        if (observed := AIS.parse_utc(r.get("observed_at")))
        and observed.date() >= first
    ]
    flags = sorted({vessel_charts.flag_label(r) for r in visible})
    current_flags = st.session_state.get(energy_key("vessel_chart_flags"), [])
    if (
        current_flags
        and ALL_SELECTION not in current_flags
        and not set(current_flags).intersection(flags)
    ):
        st.session_state[energy_key("vessel_chart_flags")] = [ALL_SELECTION]
    with columns[2]:
        selection = multiselect_with_all(
            "船籍", flags, key="vessel_chart_flags", all_label="全部"
        )
    flags = selected_values(selection, flags)
    flag_rows = [r for r in visible if vessel_charts.flag_label(r) in flags]
    destinations = sorted({vessel_charts.destination_label(r) for r in flag_rows})
    current_destinations = st.session_state.get(
        energy_key("vessel_chart_destinations"), []
    )
    if (
        current_destinations
        and ALL_SELECTION not in current_destinations
        and not set(current_destinations).intersection(destinations)
    ):
        st.session_state[energy_key("vessel_chart_destinations")] = [ALL_SELECTION]
    with columns[3]:
        selection = multiselect_with_all(
            "目的地", destinations, key="vessel_chart_destinations", all_label="全部"
        )
    destinations = selected_values(selection, destinations)
    vessels = [
        r
        for r in state.live_positions
        if vessel_charts.matches(r, flags, destinations)
        and (observed := AIS.parse_utc(r.get("observed_at")))
        and first <= observed.date() <= last
    ]
    available = any(
        (observed := AIS.parse_utc(r.get("observed_at")))
        and first <= observed.date() <= last
        for r in state.live_positions
    )
    with cards.container():
        for column, (label, value) in zip(
            st.columns(6), vessel_charts.metrics(vessels, available)
        ):
            column.metric(label, value)
    if visible:
        aggregated = vessel_charts.stock_series(
            visible, first, last, aggregation, flags, destinations
        )
        labels = vessel_charts.series_labels()
        fields = vessel_charts.CHART_FIELDS
        images = charts.vessel_chart_images(
            tuple(tuple(row[f] for f in fields) for row in aggregated), aggregation
        )
        regions = list(vessel_charts.CHART_LABELS)
        for start in range(0, len(regions), 3):
            for column, region, image in zip(
                st.columns(3), regions[start : start + 3], images[start : start + 3]
            ):
                with column:
                    st.image(image, width="stretch")
                    st.download_button(
                        "下载数据",
                        csv_export.csv_bytes(
                            [
                                {
                                    "日期": r["date"],
                                    "期间开始": r["period_start"],
                                    "期间结束": r["period_end"],
                                    "采样时刻 UTC": r.get("sample_at", ""),
                                    labels[region]: r[region],
                                }
                                for r in aggregated
                            ],
                            [
                                "日期",
                                "期间开始",
                                "期间结束",
                                "采样时刻 UTC",
                                labels[region],
                            ],
                        ),
                        file_name=f"{labels[region].replace('/', '_')}.csv",
                        mime="text/csv",
                        key=energy_key(f"vessel_chart_download_{region}"),
                        type="primary",
                    )
    else:
        st.info("所选时间范围暂无船位观测。")
    rows = dashboard_rows.vessel_rows(vessels)
    if rows:
        table_columns = {
            "船名": "船名",
            "船型": "船型",
            "船籍": "船籍",
            "航行状态": "航行状态",
            "目的地": "目的地",
            "吃水": "吃水 米",
            "纬度": "纬度",
            "经度": "经度",
            "数据源": "数据源",
        }
        st.dataframe(
            [
                {label: row.get(key) for label, key in table_columns.items()}
                for row in rows
            ],
            width="stretch",
            hide_index=True,
            height=570,
        )
        st.download_button(
            "下载船位快照 CSV",
            csv_export.csv_bytes(rows, list(rows[0])),
            file_name="ais_vessel_snapshot.csv",
            mime="text/csv",
            type="primary",
        )
