"""PortWatch download controls; data collection and encoding remain separate."""

from __future__ import annotations

from htfa.monitoring.energy_supply.widget_keys import energy_key

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

from htfa.monitoring.energy_supply import port_inventory
from htfa.monitoring.energy_supply import portwatch as PORTWATCH
from htfa.monitoring.energy_supply import portwatch_downloads
from htfa.monitoring.energy_supply.dashboard_data import portwatch_state
from htfa.monitoring.energy_supply.ui_controls import ALL_SELECTION, multiselect_with_all, selected_values


def render_download_panel(
    newest_port_day: date | None,
    newest_choke_day: date | None,
    *,
    data_revisions: dict[str, int] | None = None,
    refresh_revision: str = "initial",
) -> None:
    st.subheader("港口与咽喉要道数据")
    latest = [day for day in (newest_port_day, newest_choke_day) if day]
    default_last = max(latest) if latest else datetime.now(timezone.utc).date()
    last_downloadable = datetime.now(timezone.utc).date()

    port_catalog_rows, port_catalog_error = portwatch_state(
        "ports", "catalog", PORTWATCH.MODULE_VERSION,
        (data_revisions or {}).get("ports", 0), refresh_revision,
    )
    choke_catalog_rows, choke_catalog_error = portwatch_state(
        "chokepoints", "catalog", PORTWATCH.MODULE_VERSION,
        (data_revisions or {}).get("chokepoints", 0), refresh_revision,
    )
    if port_catalog_error or choke_catalog_error:
        st.error(
            "下载节点目录更新失败："
            + "；".join(message for message in (port_catalog_error, choke_catalog_error) if message)
        )
    if not port_catalog_rows and not choke_catalog_rows:
        return
    all_ports = [portwatch_downloads.node("ports", row) for row in port_catalog_rows]
    all_chokes = [portwatch_downloads.node("chokepoints", row) for row in choke_catalog_rows]

    kind_options = list(portwatch_downloads.KINDS)
    kinds_selection = multiselect_with_all(
        "数据类型",
        kind_options,
        key="pw_download_kinds",
        format_func=lambda value: portwatch_downloads.KINDS[value],
        placeholder="全选或选择数据类型",
    )
    selected_kinds = set(selected_values(kinds_selection, kind_options))
    scope_options = ["全部项目节点", "按条件筛选"]
    if st.session_state.get(energy_key("pw_download_scope")) not in scope_options:
        st.session_state[energy_key("pw_download_scope")] = "全部项目节点"
    scope = st.radio("节点范围", scope_options, horizontal=True, key=energy_key("pw_download_scope"))
    selected_nodes = []
    if scope == "全部项目节点":
        selected_nodes = [*all_ports, *all_chokes]
    else:
        region_options = sorted(
            {str(node.get("region")) for node in (*all_ports, *all_chokes) if node.get("region")}
        )
        regions_selection = multiselect_with_all(
            "水域", region_options, key="pw_download_regions", placeholder="全选或选择水域"
        )
        regions = set(selected_values(regions_selection, region_options))
        region_ports = [n for n in all_ports if n["region"] in regions]
        country_options = sorted(
            {n["country"] for n in region_ports if n["country"]}, key=port_inventory.country_label
        )
        countries_selection = multiselect_with_all(
            "国家",
            country_options,
            key="pw_download_countries",
            format_func=port_inventory.country_label,
            placeholder="全选或选择国家",
        )
        countries = set(selected_values(countries_selection, country_options))
        candidate_ports = [n for n in region_ports if n["country"] in countries]
        choke_options = [n for n in all_chokes if n["region"] in regions]
        node_options = [("ports", n["portid"]) for n in candidate_ports] + [
            ("chokepoints", n["portid"]) for n in choke_options
        ]
        labels = {("ports", n["portid"]): n["node_name"] for n in candidate_ports}
        labels.update({("chokepoints", n["portid"]): n["node_name"] for n in choke_options})
        nodes_selection = multiselect_with_all(
            "节点",
            node_options,
            key="pw_download_nodes",
            format_func=lambda key: labels.get(key, key[1]),
            placeholder="全选或选择节点",
        )
        chosen_nodes = set(selected_values(nodes_selection, node_options))
        selected_nodes = [n for n in candidate_ports if ("ports", n["portid"]) in chosen_nodes]
        selected_nodes += [n for n in choke_options if ("chokepoints", n["portid"]) in chosen_nodes]

    selected_nodes = [n for n in selected_nodes if n["node_kind"] in selected_kinds]

    mode = st.radio(
        "时间范围",
        ["最新数据", "历史区间", "全部可用历史"],
        horizontal=True,
        key=energy_key("pw_download_mode"),
    )
    first = last = None
    if mode == "历史区间":
        preset = st.radio(
            "日期快捷选项",
            ["近30天", "近90天", "今年以来", "自定义日期"],
            horizontal=True,
            key=energy_key("pw_download_preset"),
        )
        if preset == "自定义日期":
            current = st.session_state.get(energy_key("pw_download_dates"))
            default_start, default_end = (
                current
                if isinstance(current, (tuple, list)) and len(current) == 2
                else (
                    max(portwatch_downloads.FIRST_DAY, default_last - timedelta(days=29)),
                    default_last,
                )
            )
            dates = st.date_input(
                "UTC日期范围",
                value=(default_start, default_end),
                min_value=portwatch_downloads.FIRST_DAY,
                max_value=last_downloadable,
                key=energy_key("pw_download_dates"),
            )
            if isinstance(dates, (tuple, list)) and len(dates) == 2:
                first, last = dates
        else:
            last = default_last
            days = {"近30天": 30, "近90天": 90}.get(preset)
            first = (
                date(last.year, 1, 1)
                if preset == "今年以来"
                else max(portwatch_downloads.FIRST_DAY, last - timedelta(days=days - 1))
            )
    derived = st.checkbox("附加连续7日和30日均值", value=False, key=energy_key("pw_download_derived"))
    force = False
    if not selected_nodes:
        st.info("按条件选择至少一个数据类型与节点。")
        return

    def selection_signature():
        payload = {
            "nodes": sorted((n["node_kind"], n["portid"]) for n in selected_nodes),
            "mode": mode,
            "start": first.isoformat() if first else None,
            "end": last.isoformat() if last else None,
            "derived": derived,
            "force": force,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    signature = selection_signature()
    if st.button("生成下载数据", type="primary", key=energy_key("pw_download_generate")):
        try:
            status = st.status("正在读取数据库…", expanded=True)
            last_notice = [0.0]

            def progress(message: str):
                now = time.monotonic()
                if now - last_notice[0] >= 1.0:
                    status.update(label=message, state="running", expanded=True)
                    last_notice[0] = now

            mode_key = {"最新数据": "latest", "历史区间": "history", "全部可用历史": "all"}[mode]
            result = portwatch_downloads.collect(
                selected_nodes,
                mode_key,
                first=first,
                last=last,
                derived=derived,
                force=force,
                progress=progress,
            )
            st.session_state[energy_key("pw_download_result")] = {"signature": signature, "value": result}
            status.update(label="数据库导出已完成", state="complete", expanded=False)
        except Exception as exc:
            st.session_state.pop(energy_key("pw_download_result"), None)
            st.error(f"数据下载准备失败：{exc}")
    saved = st.session_state.get(energy_key("pw_download_result"))
    if not saved:
        return
    if saved.get("signature") != signature:
        st.info("下载条件已更改。点击“生成下载数据”以刷新导出。")
        return
    result = saved["value"]
    st.success("已按数据库记录完成导出。")
    summary = result["manifest"]["row_counts"]
    st.write(
        f"港口记录 {summary.get('ports', 0):,} 行；咽喉要道记录 "
        f"{summary.get('chokepoints', 0):,} 行；覆盖状态详见ZIP中的coverage.csv。"
    )
    slug = (
        "latest"
        if mode == "最新数据"
        else "all-history"
        if mode == "全部可用历史"
        else f"{first}_{last}"
    )
    if artifact_path := result.get("artifact_path"):
        if not Path(artifact_path).is_file():
            st.warning("分块下载文件已过期；请再次点击“生成下载数据”。")
            return
        with open(artifact_path, "rb") as archive_file:
            st.download_button(
                "下载完整 ZIP（分块 CSV、节点目录、覆盖、字典、来源查询）",
                archive_file,
                file_name=f"portwatch_{slug}.zip",
                mime="application/zip",
                key=energy_key(f"pw_download_zip_{signature[:12]}"),
            )
        return
    for kind, rows in result["datasets"].items():
        fields = portwatch_downloads.columns(kind, result["manifest"]["derived"])
        st.download_button(
            f"下载{portwatch_downloads.KINDS[kind]} CSV",
            lambda rows=rows, fields=fields: portwatch_downloads.csv_bytes(rows, fields),
            file_name=f"portwatch_{kind}_{slug}.csv",
            mime="text/csv",
            key=energy_key(f"pw_download_csv_{kind}_{signature[:12]}"),
        )
    st.download_button(
        "下载完整 ZIP（CSV、节点目录、覆盖、字典、来源查询）",
        lambda result=result: portwatch_downloads.zip_bytes(result),
        file_name=f"portwatch_{slug}.zip",
        mime="application/zip",
        key=energy_key(f"pw_download_zip_{signature[:12]}"),
    )
    records = sum(map(len, result["datasets"].values()))
    if records <= portwatch_downloads.XLSX_ROW_LIMIT:
        st.download_button(
            "下载 Excel 工作簿",
            lambda result=result: portwatch_downloads.xlsx_bytes(result),
            file_name=f"portwatch_{slug}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=energy_key(f"pw_download_xlsx_{signature[:12]}"),
        )
    else:
        st.info(
            f"当前结果超过{portwatch_downloads.XLSX_ROW_LIMIT:,}行，已提供完整CSV与ZIP下载；缩短日期范围即可下载Excel。"
        )
    left, right = st.columns(2)
    with left:
        st.dataframe(result["coverage"], width="stretch", hide_index=True, height=300)
    with right:
        st.dataframe(result["dictionary"], width="stretch", hide_index=True, height=300)
