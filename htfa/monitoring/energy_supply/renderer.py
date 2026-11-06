"""Native HTFA energy supply dashboard; reads the unified published database."""
from __future__ import annotations

from htfa.monitoring.energy_supply.widget_keys import energy_key
from pathlib import Path
import streamlit as st
from htfa.monitoring.energy_supply import ais as AIS
from htfa.monitoring.energy_supply import portwatch as PORTWATCH
from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply import report_data as _report_data_module
from htfa.monitoring.energy_supply.dashboard_data import (collector_status, load_chokepoints, load_ports,
    openwaters_snapshot, portwatch_state, initialize_storage, vessel_tracks,
    snapshot_date_bounds, nearest_portwatch_day)
from htfa.monitoring.energy_supply.dashboard_state import DashboardViewState
from htfa.monitoring.energy_supply.dashboard_views import (render_ais_panel, render_assets_panel, render_map_panel,
    prepare_monitoring_cards, render_ports_panel, render_print_report)

def render_energy_supply(st_module=st):
    """Render all four energy monitoring pages inside HTFA."""
    with st_module.container(key=energy_key("energy_supply")):
        _render_dashboard("initial")

def _render_dashboard(refresh_revision: str) -> None:

    assets = data_store.load_catalog("assets")
    style = Path(__file__).with_name("dashboard.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{style}</style>", unsafe_allow_html=True)
    st.title("中东能源与战略通道运输监测")
    initialize_storage()

    revisions = data_store.revisions(("ports", "chokepoints"))
    state_requests = {
        "ports_catalog": ("ports", "catalog", PORTWATCH.MODULE_VERSION,
                          revisions["ports"], refresh_revision),
        "chokes_catalog": ("chokepoints", "catalog", PORTWATCH.MODULE_VERSION,
                           revisions["chokepoints"], refresh_revision),
        "ports_day": ("ports", "latest_date", PORTWATCH.MODULE_VERSION,
                      revisions["ports"], refresh_revision),
        "chokes_day": ("chokepoints", "latest_date", PORTWATCH.MODULE_VERSION,
                       revisions["chokepoints"], refresh_revision),
    }
    loaded = {key: portwatch_state(*args) for key, args in state_requests.items()}
    available_ports, port_catalog_error = loaded["ports_catalog"]
    available_chokepoints, chokepoint_catalog_error = loaded["chokes_catalog"]
    newest_day, port_latest_error = loaded["ports_day"]
    newest_chokepoint_day, chokepoint_latest_error = loaded["chokes_day"]

    tab_map, tab_ports, tab_vessels, tab_assets = st.tabs(
        ["地图", "港口", "船舶", "油气"],
        key=energy_key("main_tabs"),
        on_change="rerun",
    )

    display_revisions = data_store.revisions(("ports", "chokepoints", "ais", "sea"))
    first_day, last_day = snapshot_date_bounds((str(data_store.database_path()), *display_revisions.values()))
    with tab_map:
        cards_placeholder = st.empty()
        with st.container(horizontal=True, horizontal_alignment="left"):
            snapshot_day = st.date_input(
                "选择日期", value=None, min_value=first_day, max_value=last_day,
                key=energy_key("map_snapshot_day"), format="YYYY-MM-DD", width=240,
                disabled=first_day is None,
            )
            map_search_placeholder = st.empty()
    snapshot_identity = (str(data_store.database_path()), *display_revisions.values())
    selected_day = nearest_portwatch_day("ports", snapshot_day, snapshot_identity) if snapshot_day else newest_day
    selected_chokepoint_day = nearest_portwatch_day("chokepoints", snapshot_day, snapshot_identity) if snapshot_day else newest_chokepoint_day
    selected_sea_day = (_report_data_module.card_sea_history(
        display_revisions["sea"], snapshot_day.isoformat()).get("selected_day") if snapshot_day else None)
    open_state = openwaters_snapshot(AIS.MODULE_VERSION, snapshot_day)
    live_positions = open_state.get("vessels", [])
    ais_status = collector_status()

    port_error = port_catalog_error or port_latest_error
    ports: list[dict] = []
    if selected_day is not None and available_ports:
        ports, activity_error, _ = load_ports(
            available_ports,
            selected_day,
            rolling_days=7,
            refresh_revision=refresh_revision,
            stored_revision=revisions["ports"],
        )
        port_error = "；".join(error for error in (port_error, activity_error) if error) or None
    else:
        ports = PORTWATCH.decorate(available_ports, {}, {}, None)

    chokepoint_error = chokepoint_catalog_error or chokepoint_latest_error
    chokepoints: list[dict] = []
    if selected_chokepoint_day is not None and available_chokepoints:
        chokepoints, activity_error = load_chokepoints(
            available_chokepoints,
            selected_chokepoint_day,
            refresh_revision,
            revisions["chokepoints"],
        )
        chokepoint_error = "；".join(error for error in (chokepoint_error, activity_error) if error) or None
    else:
        chokepoints = PORTWATCH.decorate_chokepoints(available_chokepoints, {})

    tracks = {}
    if tab_map.open and st.session_state.get(energy_key("map_show_vessels"), True):
        tracks = vessel_tracks(tuple((str(v["mmsi"]), v.get("observed_at"), v["lat"], v["lon"])
                                     for v in live_positions), display_revisions["ais"], str(data_store.database_path()))
    from htfa.monitoring.energy_supply import production_units as production
    saved_filters = st.session_state.get(energy_key("production_saved_filters"), {})
    chosen_assets, asset_rows, _, _ = production.statistical_view(
        assets, saved_filters.get("countries", []), saved_filters.get("products"))
    map_assets = production.map_units(assets, chosen_assets, asset_rows)
    view_state = DashboardViewState(
        live_positions=live_positions,
        ais_status=ais_status,
        open_state=open_state,
        archive_error=open_state.get("archive_error"),
        port_error=port_error,
        chokepoint_error=chokepoint_error,
        map_assets=map_assets,
        map_ports=ports,
        map_chokepoints=chokepoints,
        selected_day=selected_day,
        selected_chokepoint_day=selected_chokepoint_day,
        snapshot_day=snapshot_day,
        selected_sea_day=selected_sea_day,
        vessel_tracks=tracks,
    )

    if tab_map.open:
        with tab_map:
            cards, card_errors = prepare_monitoring_cards(
                available_ports, available_chokepoints, view_state,
                data_revisions=display_revisions,
            )
            render_map_panel(view_state, cards, cards_placeholder=cards_placeholder,
                             search_placeholder=map_search_placeholder)
            for error in card_errors:
                st.warning(f"监测卡部分指标不可用：{error}")
    if tab_ports.open:
        with tab_ports:
            render_ports_panel(
                ports,
                selected_day,
                port_error,
            )
    if tab_vessels.open:
        with tab_vessels:
            render_ais_panel(view_state)
    if tab_assets.open:
        with tab_assets:
            render_assets_panel(assets)
    render_print_report(
        available_ports, available_chokepoints, view_state,
        data_revisions=display_revisions,
    )
