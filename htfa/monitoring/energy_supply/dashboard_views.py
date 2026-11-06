"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

from htfa.monitoring.energy_supply.widget_keys import energy_key

from datetime import date

import streamlit as st
import pandas as pd

from htfa.monitoring.energy_supply import ais as AIS
from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply import csv_export
from htfa.monitoring.energy_supply import dashboard_rows
from htfa.monitoring.energy_supply import dashboard_data
from htfa.monitoring.energy_supply import port_charts
from htfa.monitoring.energy_supply import vessel_charts
from htfa.monitoring.energy_supply import map_renderer
from htfa.monitoring.energy_supply import pipeline_catalog
from htfa.monitoring.energy_supply import monitoring_cards
from datetime import datetime
from zoneinfo import ZoneInfo
from htfa.monitoring.energy_supply import portwatch as PORTWATCH
from htfa.monitoring.energy_supply import print_report
from htfa.monitoring.energy_supply import report_data
from htfa.monitoring.energy_supply.dashboard_state import DashboardViewState
from htfa.monitoring.energy_supply.map_popups import asset_popup, chokepoint_popup, port_popup
from htfa.monitoring.energy_supply.port_inventory import country_label
from htfa.monitoring.energy_supply.port_types import port_type_label, port_business_label
from htfa.monitoring.energy_supply.entity_names import display_name
from htfa.monitoring.energy_supply.ui_controls import ALL_SELECTION, multiselect_with_all, selected_values

ASSETS = data_store.load_catalog("assets")


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
    st.session_state[energy_key("map_search_request")] = {"key": key, "revision": revision}


def render_map_panel(state: DashboardViewState, summary_cards: list, *, cards_placeholder=None,
                     search_placeholder=None) -> None:
    screenshot_requested = st.session_state.pop(energy_key("map_screenshot_requested"), False)
    (cards_placeholder or st).html(monitoring_cards.cards_html(summary_cards))
    oil, gas = None, None
    try:
        oil = pipeline_catalog.load()
        gas = pipeline_catalog.load_gas_connections()
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"管线快照不可用：{exc}")
    options = map_renderer.search_objects(state.map_assets, state.map_ports,
                                         state.live_positions, oil, gas)
    labels = {row["key"]: row["label"] for row in options}
    categories = {row["key"]: row["control"] for row in options}
    if st.session_state.get(energy_key("map_search_object")) not in labels:
        st.session_state[energy_key("map_search_object")] = None
    with search_placeholder or st.container():
        st.selectbox("查找对象", list(labels), index=None, key=energy_key("map_search_object"),
                     format_func=labels.get, placeholder="输入油气、港口、船舶或管线名称",
                     on_change=queue_map_focus, args=(categories,))
    with st.container(horizontal=True, key=energy_key("map_layer_filters")):
        show_assets = st.checkbox("油气", value=True, key=energy_key("map_show_assets"))
        show_ports = st.checkbox("港口", value=True, key=energy_key("map_show_ports"))
        show_vessels = st.checkbox("船舶", value=True, key=energy_key("map_show_vessels"))
        show_pipelines = st.checkbox("输油管线", value=True, key=energy_key("map_show_pipelines"))
        show_gas = st.checkbox("输气管线", value=True, key=energy_key("map_show_gas"))
    pipelines = None
    if show_pipelines:
        try:
            pipelines = oil
        except (FileNotFoundError, ValueError) as exc:
            st.error(f"输油管线快照不可用：{exc}")
    if show_gas:
        try:
            pipelines = {"type": "FeatureCollection", "features": [*(pipelines or {}).get("features", []), *(gas or {}).get("features", [])]}
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
    port_day = state.selected_day if snapshot_day is None or any(p.get("has_data") for p in state.map_ports) else None
    choke_day = state.selected_chokepoint_day if snapshot_day is None or any(p.get("has_data") for p in state.map_chokepoints) else None
    st.iframe(
        map_renderer.build_map_html(
            state.map_assets if show_assets else [],
            state.map_ports if show_ports else [],
            state.map_chokepoints if show_ports else [],
            state.live_positions if show_vessels else [],
            port_day.isoformat() if port_day else "无数据",
            choke_day.isoformat()
            if choke_day
            else "无数据",
            visible_categories={name for name, selected in (
                ("assets", show_assets), ("ports", show_ports), ("vessels", show_vessels)
            ) if selected},
            asset_popup=asset_popup,
            port_popup=port_popup,
            chokepoint_popup=chokepoint_popup,
            screenshot_requested=screenshot_requested,
            vessel_tracks=getattr(state, "vessel_tracks", None) if show_vessels else None,
            pipelines=pipelines,
            snapshot_day=snapshot_day.isoformat() if snapshot_day else None,
            sea_day=(getattr(state, "selected_sea_day", None).isoformat()
                     if getattr(state, "selected_sea_day", None) else None),
            focus_request=st.session_state.get(energy_key("map_search_request")),
        ),
        height=735,
    )
    if show_assets:
        unlocated = [row for asset in state.map_assets if not asset.get("map_drawable")
                     for row in asset.get("production_rows", [])]
        if unlocated:
            st.warning(f"{len(unlocated)}条油气记录缺少可靠坐标，以下保留与油气表一致的信息，暂不上图。")
            st.dataframe(pd.DataFrame(unlocated), hide_index=True, width="stretch",
                         column_config={"数据来源": st.column_config.LinkColumn("数据来源")})
    with st.container(horizontal=True, key=energy_key("map_refresh_actions")):
        st.button("保存图片", type="primary", width="content",
                  on_click=queue_map_screenshot)


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
        period = st.selectbox("时间范围", port_charts.TIME_RANGES, index=4, key=energy_key("vessel_chart_period"))
    with columns[1]:
        aggregation = st.selectbox("聚合方式", list(port_charts.AGGREGATIONS), key=energy_key("vessel_chart_aggregation"))
    last = state.snapshot_day or AIS.utc_now().date()
    path = data_store.database_path()
    identity = (str(path), path.stat().st_mtime_ns)
    history = vessel_charts.history(last, identity)
    earliest = min((AIS.parse_utc(r["observed_at"]).date() for r in history), default=last)
    first = port_charts.window_start(last, period, earliest)
    visible = [r for r in history if (observed := AIS.parse_utc(r.get("observed_at"))) and observed.date() >= first]
    flags = sorted({vessel_charts.flag_label(r) for r in visible})
    current_flags = st.session_state.get(energy_key("vessel_chart_flags"), [])
    if current_flags and ALL_SELECTION not in current_flags and not set(current_flags).intersection(flags):
        st.session_state[energy_key("vessel_chart_flags")] = [ALL_SELECTION]
    with columns[2]:
        selection = multiselect_with_all("船籍", flags, key="vessel_chart_flags", all_label="全部")
    flags = selected_values(selection, flags)
    flag_rows = [r for r in visible if vessel_charts.flag_label(r) in flags]
    destinations = sorted({vessel_charts.destination_label(r) for r in flag_rows})
    current_destinations = st.session_state.get(energy_key("vessel_chart_destinations"), [])
    if current_destinations and ALL_SELECTION not in current_destinations and not set(current_destinations).intersection(destinations):
        st.session_state[energy_key("vessel_chart_destinations")] = [ALL_SELECTION]
    with columns[3]:
        selection = multiselect_with_all("目的地", destinations, key="vessel_chart_destinations", all_label="全部")
    destinations = selected_values(selection, destinations)
    vessels = [r for r in state.live_positions if vessel_charts.matches(r, flags, destinations)
               and (observed := AIS.parse_utc(r.get("observed_at"))) and first <= observed.date() <= last]
    available = any((observed := AIS.parse_utc(r.get("observed_at"))) and first <= observed.date() <= last
                    for r in state.live_positions)
    with cards.container():
        for column, (label, value) in zip(st.columns(6), vessel_charts.metrics(vessels, available)):
            column.metric(label, value)
    if visible:
        aggregated = vessel_charts.stock_series(visible, first, last, aggregation, flags, destinations)
        labels = vessel_charts.series_labels()
        fields = vessel_charts.CHART_FIELDS
        images = vessel_charts.chart_images(tuple(tuple(row[f] for f in fields) for row in aggregated), aggregation)
        regions = list(vessel_charts.CHART_LABELS)
        for start in range(0, len(regions), 3):
            for column, region, image in zip(st.columns(3), regions[start:start+3], images[start:start+3]):
                with column:
                    st.image(image, width="stretch")
                    st.download_button(
                        "下载数据",
                        csv_export.csv_bytes([{"日期": r["date"], "期间开始": r["period_start"],
                                               "期间结束": r["period_end"],
                                               "采样时刻 UTC": r.get("sample_at", ""), labels[region]: r[region]}
                                              for r in aggregated],
                                             ["日期", "期间开始", "期间结束", "采样时刻 UTC", labels[region]]),
                        file_name=f"{labels[region].replace('/', '_')}.csv", mime="text/csv",
                        key=energy_key(f"vessel_chart_download_{region}"), type="primary")
    else:
        st.info("所选时间范围暂无船位观测。")
    rows = dashboard_rows.vessel_rows(vessels)
    if rows:
        table_columns = {
            "船名": "船名", "船型": "船型", "船籍": "船籍",
            "航行状态": "航行状态", "目的地": "目的地", "吃水": "吃水 米",
            "纬度": "纬度", "经度": "经度", "数据源": "数据源",
        }
        st.dataframe(
            [{label: row.get(key) for label, key in table_columns.items()} for row in rows],
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


def _port_chart_filters(ports: list[dict]) -> tuple[str, list[dict], str]:
    columns = st.columns([1.1, 1, 1, 1, 1.6, 1.8])
    with columns[0]:
        period = st.selectbox("时间范围", port_charts.TIME_RANGES, index=4, key=energy_key("port_chart_period"))
    with columns[1]:
        aggregation = st.selectbox("聚合方式", list(port_charts.AGGREGATIONS), key=energy_key("port_chart_aggregation"))
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
        if current and ALL_SELECTION not in current and not set(current).intersection(options):
            st.session_state[energy_key(key)] = [ALL_SELECTION]
        with column:
            selection = multiselect_with_all(label, options, key=key, format_func=formatter, all_label="全部")
        selected = set(selected_values(selection, options))
        filtered = [port for port in filtered if value_of(port) in selected]
    return period, filtered, aggregation


def render_ports_panel(ports: list[dict], selected_day: date | None, port_error: str | None) -> None:
    listed_ports = ports
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    metrics = dashboard_rows.port_metrics(ports, selected_day)
    for start in range(0, len(metrics), 4):
        for column, (label, value) in zip(st.columns(4), metrics[start:start+4]):
            column.metric(label, value)
    if selected_day:
        period, chart_ports, aggregation = _port_chart_filters(ports)
        listed_ports = chart_ports
        port_ids = tuple(sorted({str(p["portid"]) for p in chart_ports if PORTWATCH.has_independent_statistics(p)}))
        path = data_store.database_path()
        history = dashboard_data.port_time_series(port_ids, selected_day, (str(path), path.stat().st_mtime_ns))
        if history:
            first = port_charts.window_start(selected_day, period, history[0]["date"])
            fields = ["date", "portcalls", *(f"portcalls_{kind}" for kind in PORTWATCH.SHIP_TYPES)]
            rows = tuple(tuple(row[field] for field in fields) for row in history)
            images = port_charts.chart_images(rows, first, aggregation)
            series = list(port_charts.series_labels(aggregation).items())
            visible_history = port_charts.aggregate_rows(rows, first, aggregation)
            for start in (0, 3):
                for column, image, (field, title) in zip(st.columns(3), images[start:start+3], series[start:start+3]):
                    with column:
                        st.image(image, width="stretch")
                        st.download_button(
                            "下载数据",
                            data=csv_export.csv_bytes(
                                [{"日期": row["date"], **({"期间开始": row["period_start"], "期间结束": row["period_end"]}
                                  if aggregation != "日度" else {}), title: row[field]} for row in visible_history],
                                ["日期", *(["期间开始", "期间结束"] if aggregation != "日度" else []), title],
                            ),
                            file_name=f"{title.replace('/', '_')}.csv",
                            mime="text/csv",
                            key=energy_key(f"port_chart_download_{field}"),
                            type="primary",
                            on_click="ignore",
                        )
        else:
            st.info("所选港口暂无独立进港统计" if chart_ports else "没有符合筛选条件的港口")
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
                **{name: st.column_config.NumberColumn(format="%d") for name in port_rows[0] if name.endswith("艘次")},
            },
        )
        st.download_button(
            "下载列表",
            csv_export.csv_bytes(port_rows, list(port_rows[0])),
            file_name=f"portwatch_ports_{selected_day.isoformat() if selected_day else 'unknown'}.csv",
            mime="text/csv",
            type="primary",
        )



def render_assets_panel(assets: list[dict]) -> None:
    from htfa.monitoring.energy_supply import production_units as production

    assets = [asset for asset in assets if asset["country"] != "土耳其"]
    metrics_container = st.container()
    c1, c2 = st.columns(2)
    country_options = sorted({c for a in assets for c in (a.get("countries") or [a["country"]]) if c != "土耳其"})
    if energy_key("production_countries") in st.session_state:
        st.session_state[energy_key("production_countries")] = [c for c in st.session_state[energy_key("production_countries")] if c in country_options]
    saved = st.session_state.get(energy_key("production_saved_filters"), {})
    countries = c1.multiselect("国家", country_options,
                               default=[c for c in saved.get("countries", []) if c in country_options],
                               key=energy_key("production_countries"))
    product_labels = c2.multiselect("商品", list(production.STATISTICAL_PRODUCTS.values()),
                                      default=[production.STATISTICAL_PRODUCTS[p] for p in saved.get("products", list(production.STATISTICAL_PRODUCTS))
                                               if p in production.STATISTICAL_PRODUCTS], key=energy_key("production_products"))
    products = [key for key, label in production.STATISTICAL_PRODUCTS.items() if label in product_labels]
    st.session_state[energy_key("production_saved_filters")] = {"countries": countries, "products": products}
    chosen, rows, daily_column, _ = production.statistical_view(assets, countries, products)
    with metrics_container:
        a1, active, a2, a3, a4 = st.columns([1, 1, 1, 1, 2])
        a1.metric("油田资产数量", len(rows))
        active.metric("在产数量", production.producing_count(chosen))
        a2.metric("国家数量", len({c for o in chosen for c in o["countries"]}))
        a3.metric("油田类型数量", len({row["类型"] for row in rows}))
        crude_values = [row[daily_column] for row in rows
                        if row["商品"] == "原油" and row[daily_column] is not None]
        amount = f"{sum(crude_values):.1f}万桶/日" if crude_values else "—"
        with a4.container(key=energy_key("production_daily_metric")):
            st.metric("原油产量", amount)
    table = pd.DataFrame(rows, columns=["名称", "国家", "类型", "包含资产", daily_column,
                                        "商品", "状态", "备注", "数据时间", "数据来源"])
    table[daily_column] = pd.to_numeric(table[daily_column], errors="coerce")
    st.dataframe(
        table, width="stretch", hide_index=True, height=620,
        column_config={"数据来源": st.column_config.LinkColumn("数据来源"),
                       daily_column: st.column_config.NumberColumn(daily_column)},
    )

    st.download_button(
        "下载数据", csv_export.csv_bytes(rows, list(table.columns)),
        file_name="oil_gas_production.csv", mime="text/csv", type="primary",
        key=energy_key("production_download"), on_click="ignore",
    )


def render_method_panel() -> None:
    st.subheader("范围、口径与数据限制")
    st.markdown(
        "**更新方式。** 展示端只读GitHub发布快照，不联网采集或写库；数据由既有采集发布脚本统一更新。"
    )
    st.dataframe(
        [
            {
                "数据": "港口 / 咽喉点日度记录",
                "当前更新": "采集端更新成功后发布日度记录，同一节点同一天去重更新",
                "进一步自动化": "源站发布时间决定最新观测日；缺失仍保持未知",
            },
            {
                "数据": "实时船位",
                "当前更新": "展示已发布船位快照；选择日期时读取当天归档",
                "进一步自动化": "覆盖与采集频率决定实时性，展示端不启动采集服务",
            },
            {
                "数据": "港口 / 咽喉点官方目录",
                "当前更新": "读取已发布的版本化目录",
                "进一步自动化": "补充 WPI / 运营商名录仍需版本核验",
            },
            {
                "数据": "港口风险运力",
                "当前更新": "既有采集任务尝试更新并归档；港口页不再展示该模型",
                "进一步自动化": "源为历史航线模型；重新抓取不代表实时风险",
            },
            {
                "数据": "油气产量、产能、状态和坐标",
                "当前更新": "带来源的静态披露；公开目录参考点另标版本和精度限制",
                "进一步自动化": "接运营商 / 监管机构 API 或公告抓取，校验资产、日期、单位、产量 / 产能后更新",
            },
            {
                "数据": "油气运营商、权益、发现年和投产年",
                "当前更新": "Global Energy Monitor 2026-03公开镜像参考（CC BY 4.0）；不代表当前在产",
                "进一步自动化": "新版本需核对名称和层级；原字段缺失保持为空，不填补日产量",
            },
            {
                "数据": "船位归档",
                "当前更新": "归档有明确观测时间的上游快照；接收时间另存，地图与船舶页展示已存最新快照",
                "进一步自动化": "统一DuckDB由Git LFS发布；保留真实观测，不以稀疏船位推断完整流量",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "**地图与截图。** 港口和咽喉点分别使用源站最新观测日，船舶图层显示当前AIS快照；油气保留披露日期。地图下方的“保存图片”按钮可导出当前视野、图例、日期、弹窗及底图署名。"
    )
    st.markdown(
        "**港口覆盖。** 地图读取 IMF 当前维护的 PortWatch 港口点位数据库，"
        "覆盖下表五个水域框及沙特、阿联酋、伊拉克、伊朗、科威特、卡塔尔、阿曼、巴林全境的源库港口。"
        "另补港务局、运营商及NGA具名设施；无独立统计的设施保留未知，无可靠坐标时仅列目录。"
    )
    st.dataframe(
        [
            {"水域": name, "南界": b[0], "北界": b[1], "西界": b[2], "东界": b[3]}
            for name, b in PORTWATCH.REGIONS.items()
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        f"[IMF PortWatch 方法说明]({PORTWATCH.SOURCE}) · "
        "[当前港口点位 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0) · "
        "[每日港口活动 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0) · "
        "[每日咽喉点 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0) · "
        "[风险运力网络 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/spillovers_port_level_impact/FeatureServer/0)"
    )
    st.markdown("**港口指标。** 港口页与地图弹窗的本周累计为所显示数据日所在周周一至当天；船型占比为分类累计艘次除以本周总艘次。缺报保留未知，下载中的滚动窗口指标按对应字段口径计算。")
    st.dataframe(
        [
            {
                "指标": "港口活动指数",
                "计算": "当前窗口日均有效进港艘次 ÷ 前一等长窗口日均值 × 100",
                "解释": "100持平；高于100表示进港活动增加",
            },
            {
                "指标": "船型结构",
                "计算": "窗口内各船型进港艘次 ÷ 全部进港艘次",
                "解释": "集装箱、干散货、普通货物、滚装、油轮/液货船",
            },
            {
                "指标": "活跃天数率",
                "计算": "窗口内有效进港艘次大于0的天数 ÷ 窗口天数",
                "解释": "反映港口活动连续性",
            },
            {
                "指标": "单船平均货量",
                "计算": "窗口内估算进口量与出口量之和 ÷ 有效进港艘次",
                "解释": "单位万吨/艘次；属于AIS载荷估算",
            },
            {
                "指标": "进出口平衡指数",
                "计算": "(出口量−进口量) ÷ (出口量+进口量) × 100",
                "解释": "−100进口导向；+100出口导向",
            },
            {
                "指标": "风险运力",
                "计算": "该港所有出港航线 daily_capacity_at_risk 之和",
                "解释": "2019—2024历史航线网络冲击暴露，非实时值",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "PortWatch 的 portcalls 是进入港界并通过贸易挂靠筛选的有效进港艘次，不是在港船舶存量；"
        "货量根据 AIS、载重和吃水估算。单日 0 只表示源表当日为 0；窗口不完整或比较基期为 0 时，"
        "派生指标保持为空，不以 0 替代。tanker 可能包含原油、成品油及其他液体货物。"
    )
    st.markdown(
        f"**船舶数据。** 免费快照来自[Open Waters开放AIS网络]({AIS.OPENWATERS_SOURCE})，"
        f"可选[AISStream WebSocket API]({AIS.SOURCE})在服务器端接收五个监测水域及红海北、南段的船级广播；"
        "船位快照用于地图、船舶页和后台打印报告；每次运行自动获取并保存最新船位，保留实际观测时间，获取失败时沿用已存快照。"
        "浏览器只接收标准化的每船最新位置，不接收API Key。"
        "多源位置按MMSI合并，航行阈值为0.5节；"
        "上游来源署名随船舶表及弹窗显示。"
    )
    st.markdown(
        "AIS 基础船型只能可靠区分油轮／液货船、货船、客船等大类，不能直接识别集装箱船、干散货船、"
        "原油油轮或成品油轮。AIS 是事件驱动广播，覆盖中断、设备关闭、错误 MMSI、延迟或位置欺骗都会造成缺失；"
        "未收到报文不等于水域内船舶数为 0。实时船位不能替代 PortWatch 按港界和贸易规则处理的日度挂靠指标。"
    )
    st.markdown(
        "**咽喉点。** 打印地图的空心紫色圆点标示全部监测咽喉点。"
        "popup列示总通过船数、估算承载货量及五类船型分解；港口和咽喉点默认分别使用最新观测日；选择历史日期时，各来源采用最近有效记录日，缺报不补零。"
    )
    st.markdown(
        f"**资产覆盖与战略层级（公开目录，非全量保证）。** 目录保留全部{len(ASSETS)}项公开命名的生产、开发、发现或历史资产；"
        f"地图显示其中{sum(a['map_drawable'] for a in ASSETS)}个具备可绘制坐标的资产。"
        "上级油田群、区块或特许区有"
        "直接披露值时，地图和目录按资产层级分别列示；上级缺坐标时可使用已定位组成"
        "资产的几何中心，并在弹窗中明确标注。"
    )
    st.markdown(
        "**坐标质量。** 地图优先使用资产级公开WGS84点位；区块缺少直接点位时，可使用组成油田"
        "或公开设施的代表点／几何中心；组成单田仍缺点位时，可使用最近上级资产代表点。此类坐标"
        "明确标为“近似”，只用于地图定位，不代表区块边界、储层范围或精确井位。坐标证据链接可在"
        "popup和资产表中追溯。"
    )
    st.markdown(
        "**产量与产能。** 油气统一使用橙色叉号；指标性质、数据日期和披露情况在弹窗及表格中列明。"
        "实际产量、历史产量、产能、目标和规划增量分别标注；未披露数值不视为零。不同日期、商品和权益口径"
        "不得相加。来源为千桶/日的油品数值在界面统一换算为万桶/日；生产状态带证据时点，"
        "不等于实时遥测。"
    )


def prepare_monitoring_cards(available_ports, available_chokepoints, state,
                             port_history=None, choke_history=None,
                             data_revisions=None, port_comparison=None,
                             choke_comparison=None):
    """Prepare summary cards from local data or explicitly supplied report data."""
    errors = []
    revisions = data_revisions or {}
    port_ids = tuple(sorted(str(p["portid"]) for p in available_ports
                            if PORTWATCH.has_independent_statistics(p)))
    choke_ids = tuple(sorted(str(p["portid"]) for p in available_chokepoints))
    histories = []
    for kind, ids, day, supplied in (
        ("ports", port_ids, state.selected_day, port_history),
        ("chokepoints", choke_ids, state.selected_chokepoint_day, choke_history),
    ):
        rows = supplied
        if rows is None:
            rows = []
            if ids and day:
                try:
                    rows = report_data.card_activity_history(
                        kind, ids, day.isoformat(), revisions.get(kind, 0)
                    )
                except Exception as exc:
                    errors.append(f"{kind} 本地历史窗口：{type(exc).__name__}: {exc}")
        histories.append(rows)
    port_history, choke_history = histories
    comparison_ports = port_comparison or []
    comparison_chokes = choke_comparison or []
    cards = monitoring_cards.build_cards(
        available_ports, available_chokepoints,
        port_history + comparison_ports, choke_history + comparison_chokes,
        state.selected_day, state.selected_chokepoint_day,
        assets=state.map_assets,
    )
    return cards, errors


def render_print_report(
    available_ports: list[dict], available_chokepoints: list[dict], state: DashboardViewState,
    *, data_revisions: dict[str, int] | None = None,
) -> None:
    selected_day = state.selected_day
    selected_chokepoint_day = state.selected_chokepoint_day
    live_positions = state.live_positions
    port_error = state.port_error
    chokepoint_error = state.chokepoint_error
    open_state = state.open_state
    report_port_catalog = list(available_ports)
    report_choke_catalog = list(available_chokepoints)
    report_assets = list(ASSETS)
    report_vessels = [
        {
            key: vessel.get(key)
            for key in (
                "mmsi", "name", "lat", "lon", "region", "category", "category_label", "moving",
                "observed_at", "received_at",
            )
        }
        for vessel in live_positions
    ]

    report_port_ids = tuple(
        sorted(
            str(port["portid"])
            for port in report_port_catalog
            if PORTWATCH.has_independent_statistics(port)
        )
    )
    report_choke_ids = tuple(sorted(str(point["portid"]) for point in report_choke_catalog))
    report_errors = []
    revisions = data_revisions or {}
    if port_error:
        report_errors.append(f"港口最新数据：{port_error}")
    if chokepoint_error:
        report_errors.append(f"咽喉点最新数据：{chokepoint_error}")
    if open_state.get("error"):
        report_errors.append(f"Open Waters：{open_state['error']}")

    report_port_history = []
    report_choke_history = []
    if selected_day is not None and report_port_ids:
        try:
            report_port_history = report_data.history_window(
                "ports", report_port_ids, selected_day.isoformat(),
                revisions.get("ports", 0), allow_network=False,
            )
        except Exception as exc:
            report_errors.append(f"ports 历史窗口：{type(exc).__name__}: {exc}")
    if selected_chokepoint_day is not None and report_choke_ids:
        try:
            report_choke_history = report_data.history_window(
                "chokepoints",
                report_choke_ids,
                selected_chokepoint_day.isoformat(),
                revisions.get("chokepoints", 0), allow_network=False,
            )
        except Exception as exc:
            report_errors.append(f"chokepoints 历史窗口：{type(exc).__name__}: {exc}")

    report_port_comparison, report_choke_comparison = [], []
    for kind, ids, day, target in (
        ("ports", report_port_ids, selected_day, report_port_comparison),
        ("chokepoints", report_choke_ids, selected_chokepoint_day, report_choke_comparison),
    ):
        if day is None or not ids:
            continue
        try:
            target.extend(report_data.comparison_history(
                kind, ids, day.isoformat(), revisions.get(kind, 0), allow_network=False
            ))
        except Exception as exc:
            report_errors.append(f"{kind} 同比记录：{type(exc).__name__}: {exc}")

    cards, card_errors = prepare_monitoring_cards(
        report_port_catalog, report_choke_catalog, state,
        report_port_history, report_choke_history,
        data_revisions=revisions,
        port_comparison=report_port_comparison,
        choke_comparison=report_choke_comparison,
    )
    report_errors.extend(card_errors)

    report_latest_ports = report_data.merge_latest_rows(report_port_catalog, report_port_history)

    report_asset_table = [dashboard_rows.print_asset_record(asset) for asset in report_assets]
    report_ais_state = state.ais_status
    report_ais_status = str(report_ais_state.get("status") or "等待数据")
    report_observed_at = max((vessel.get("observed_at") or "" for vessel in live_positions), default="")
    report_ais_note = (
        f"Open Waters 快照 {len(open_state.get('vessels') or [])} 艘；"
        f"观测截至 {report_observed_at or '未提供'}；"
        f"AISStream 状态：{report_ais_status}"
    )
    report_html = report_data.cached_print_report({
        "scope_label": "全部监测对象",
        "monitoring_summary_cards": cards,
        "generated_at": None,
        "port_catalog": report_port_catalog,
        "choke_catalog": report_choke_catalog,
        "latest_ports": report_latest_ports,
        "port_history": report_port_history,
        "choke_history": report_choke_history,
        "assets": report_assets,
        "asset_table": report_asset_table,
        "vessels": report_vessels,
        "regions": PORTWATCH.REGIONS,
        "port_day": selected_day,
        "choke_day": selected_chokepoint_day,
        "ais_status": report_ais_status,
        "ais_source_note": report_ais_note,
        "errors": report_errors,
    })
    st.html(print_report.PRINT_CSS + report_html)
