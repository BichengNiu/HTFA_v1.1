"""Native energy dashboard composition and navigation."""

from pathlib import Path

import streamlit as st

from htfa.monitoring.energy_supply.contracts import DashboardQuery
from htfa.monitoring.energy_supply.processing import dashboard_service, reporting

from . import cache
from .assets_panel import render_assets_panel
from .map_panel import render_map_panel
from .ports_panel import render_ports_panel
from .report_panel import render_print_report
from .vessels_panel import render_ais_panel
from .widget_keys import energy_key


def render_energy_supply(st_module=st):
    """Render the four native pages from a read-only published snapshot."""
    with st_module.container(key=energy_key("energy_supply")):
        _render_dashboard()


def _render_dashboard():
    style = Path(__file__).with_name("dashboard.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{style}</style>", unsafe_allow_html=True)
    st.title("中东能源与战略通道运输监测")
    context = cache.dashboard_context()
    tab_map, tab_ports, tab_vessels, tab_assets = st.tabs(
        ["地图", "港口", "船舶", "油气"], key=energy_key("main_tabs"), on_change="rerun"
    )
    with tab_map:
        cards_placeholder = st.empty()
        with st.container(horizontal=True, horizontal_alignment="left"):
            selected_day = st.date_input(
                "选择日期",
                value=None,
                min_value=context.first_day,
                max_value=context.last_day,
                key=energy_key("map_snapshot_day"),
                format="YYYY-MM-DD",
                width=240,
                disabled=context.first_day is None,
            )
            search_placeholder = st.empty()
    filters = st.session_state.get(energy_key("production_saved_filters"), {})
    products = filters.get("products")
    query = DashboardQuery(
        selected_day,
        tab_map.open and st.session_state.get(energy_key("map_show_vessels"), True),
        tuple(filters.get("countries", [])),
        tuple(products) if products is not None else None,
    )
    state = dashboard_service.prepare_snapshot(context, query)
    if tab_map.open:
        with tab_map:
            cards, errors = reporting.prepare_monitoring_cards(
                context.ports,
                context.chokepoints,
                state,
                data_revisions=context.revisions,
            )
            render_map_panel(
                state,
                cards,
                cards_placeholder=cards_placeholder,
                search_placeholder=search_placeholder,
            )
            for error in errors:
                st.warning(f"监测卡部分指标不可用：{error}")
    if tab_ports.open:
        with tab_ports:
            render_ports_panel(state.map_ports, state.selected_day, state.port_error)
    if tab_vessels.open:
        with tab_vessels:
            render_ais_panel(state)
    if tab_assets.open:
        with tab_assets:
            render_assets_panel(context.assets)
    render_print_report(
        context.ports, context.chokepoints, state, data_revisions=context.revisions
    )
