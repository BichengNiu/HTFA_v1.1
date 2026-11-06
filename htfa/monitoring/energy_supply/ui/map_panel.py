"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import htfa.monitoring.energy_supply.processing.pipeline_catalog as pipeline_catalog
import htfa.monitoring.energy_supply.ui.map_renderer as map_renderer
from htfa.monitoring.energy_supply.contracts import DashboardViewState
from htfa.monitoring.energy_supply.ui.map_popups import (
    asset_popup,
    chokepoint_popup,
    port_popup,
)
from htfa.monitoring.energy_supply.ui.widget_keys import energy_key

from . import card_html


def queue_map_screenshot() -> None:
    st.session_state[energy_key("map_screenshot_requested")] = True


def queue_map_focus(categories: dict) -> None:
    key = st.session_state.get(energy_key("map_search_object"))
    if not key:
        return
    category = categories.get(key)
    if category:
        st.session_state[energy_key(category)] = True
    revision = st.session_state.get(energy_key("map_search_revision"), 0) + 1
    st.session_state[energy_key("map_search_revision")] = revision
    st.session_state[energy_key("map_search_request")] = {
        "key": key,
        "revision": revision,
    }


def render_map_panel(
    state: DashboardViewState,
    summary_cards: list,
    *,
    cards_placeholder=None,
    search_placeholder=None,
) -> None:
    screenshot_requested = st.session_state.pop(
        energy_key("map_screenshot_requested"), False
    )
    (cards_placeholder or st).html(card_html.cards_html(summary_cards))
    oil, gas = None, None
    try:
        oil = pipeline_catalog.load()
        gas = pipeline_catalog.load_gas_connections()
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"管线快照不可用：{exc}")
    options = map_renderer.search_objects(
        state.map_assets, state.map_ports, state.live_positions, oil, gas
    )
    labels = {row["key"]: row["label"] for row in options}
    categories = {row["key"]: row["control"] for row in options}
    if st.session_state.get(energy_key("map_search_object")) not in labels:
        st.session_state[energy_key("map_search_object")] = None
    with search_placeholder or st.container():
        st.selectbox(
            "查找对象",
            list(labels),
            index=None,
            key=energy_key("map_search_object"),
            format_func=labels.get,
            placeholder="输入油气、港口、船舶或管线名称",
            on_change=queue_map_focus,
            args=(categories,),
        )
    with st.container(horizontal=True, key=energy_key("map_layer_filters")):
        show_assets = st.checkbox("油气", value=True, key=energy_key("map_show_assets"))
        show_ports = st.checkbox("港口", value=True, key=energy_key("map_show_ports"))
        show_vessels = st.checkbox(
            "船舶", value=True, key=energy_key("map_show_vessels")
        )
        show_pipelines = st.checkbox(
            "输油管线", value=True, key=energy_key("map_show_pipelines")
        )
        show_gas = st.checkbox("输气管线", value=True, key=energy_key("map_show_gas"))
    pipelines = None
    if show_pipelines:
        try:
            pipelines = oil
        except (FileNotFoundError, ValueError) as exc:
            st.error(f"输油管线快照不可用：{exc}")
    if show_gas:
        try:
            pipelines = {
                "type": "FeatureCollection",
                "features": [
                    *(pipelines or {}).get("features", []),
                    *(gas or {}).get("features", []),
                ],
            }
        except (FileNotFoundError, ValueError) as exc:
            st.error(f"输气管线快照不可用：{exc}")
    stream_state = state.ais_status
    if state.port_error:
        st.error(f"港口数据加载失败：{state.port_error}")
    if state.chokepoint_error:
        st.error(f"咽喉点数据加载失败：{state.chokepoint_error}")
    if state.archive_error:
        st.error(state.archive_error)
    if state.open_state.get("error"):
        st.error(f"Open Waters 快照加载失败：{state.open_state['error']}")
    if stream_state.get("last_error") and not state.live_positions:
        st.error(f"AISStream 暂无可用船位：{stream_state['last_error']}")
    snapshot_day = getattr(state, "snapshot_day", None)
    port_day = (
        state.selected_day
        if snapshot_day is None or any(p.get("has_data") for p in state.map_ports)
        else None
    )
    choke_day = (
        state.selected_chokepoint_day
        if snapshot_day is None or any(p.get("has_data") for p in state.map_chokepoints)
        else None
    )
    st.iframe(
        map_renderer.build_map_html(
            state.map_assets if show_assets else [],
            state.map_ports if show_ports else [],
            state.map_chokepoints if show_ports else [],
            state.live_positions if show_vessels else [],
            port_day.isoformat() if port_day else "无数据",
            choke_day.isoformat() if choke_day else "无数据",
            visible_categories={
                name
                for name, selected in (
                    ("assets", show_assets),
                    ("ports", show_ports),
                    ("vessels", show_vessels),
                )
                if selected
            },
            asset_popup=asset_popup,
            port_popup=port_popup,
            chokepoint_popup=chokepoint_popup,
            screenshot_requested=screenshot_requested,
            vessel_tracks=getattr(state, "vessel_tracks", None)
            if show_vessels
            else None,
            pipelines=pipelines,
            snapshot_day=snapshot_day.isoformat() if snapshot_day else None,
            sea_day=(
                getattr(state, "selected_sea_day", None).isoformat()
                if getattr(state, "selected_sea_day", None)
                else None
            ),
            focus_request=st.session_state.get(energy_key("map_search_request")),
        ),
        height=735,
    )
    if show_assets:
        unlocated = [
            row
            for asset in state.map_assets
            if not asset.get("map_drawable")
            for row in asset.get("production_rows", [])
        ]
        if unlocated:
            st.warning(
                f"{len(unlocated)}条油气记录缺少可靠坐标，以下保留与油气表一致的信息，暂不上图。"
            )
            st.dataframe(
                pd.DataFrame(unlocated),
                hide_index=True,
                width="stretch",
                column_config={"数据来源": st.column_config.LinkColumn("数据来源")},
            )
    with st.container(horizontal=True, key=energy_key("map_refresh_actions")):
        st.button(
            "保存图片", type="primary", width="content", on_click=queue_map_screenshot
        )
