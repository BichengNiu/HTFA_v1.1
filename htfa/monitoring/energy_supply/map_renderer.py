"""Pure Leaflet map HTML renderer; UI state stays in the Streamlit page."""
from __future__ import annotations

from htfa.monitoring.energy_supply.entity_names import display_name

import json
from pathlib import Path

from htfa.monitoring.energy_supply import ais as AIS
from htfa.monitoring.energy_supply import map_tools
from htfa.monitoring.energy_supply import pipeline_catalog
from htfa.monitoring.energy_supply.html_transport import compressed_document
from htfa.monitoring.energy_supply.vessel_display import destination_label, reception_time, source_label

# Bundle the fixed map dependencies so drawing ships does not wait for a CDN.
_VENDOR = Path(__file__).with_name("vendor") / "leaflet"
_MAP_STYLES = "\n".join((_VENDOR / name).read_text() for name in (
    "leaflet.css", "MarkerCluster.css", "MarkerCluster.Default.css"))
_MAP_SCRIPTS = "\n".join((_VENDOR / name).read_text() for name in (
    "leaflet.js", "leaflet.markercluster.js"))


def search_objects(assets, ports, vessels, oil=None, gas=None):
    """Stable identities; names are labels, never lookup keys."""
    rows = []
    for asset in assets:
        if ((asset.get("map_drawable") and not asset.get("map_is_proxy", False))
                or asset.get("production_rows")):
            rows.append({"key": f'asset:{asset.get("country", "")}\x1f{asset["name"]}',
                         "label": "油气 · " + display_name(asset), "control": "map_show_assets"})
    for port in ports:
        rows.append({"key": f'port:{port["portid"]}', "label": "港口 · " + display_name(port),
                     "control": "map_show_ports"})
    for vessel in vessels:
        rows.append({"key": f'vessel:{vessel["mmsi"]}',
                     "label": f'船舶 · {vessel.get("name") or vessel["mmsi"]} · {vessel["mmsi"]}',
                     "control": "map_show_vessels"})
    for document in (oil, gas):
        for feature in (document or {}).get("features", []):
            p = feature["properties"]
            if not p.get("map_drawable", True):
                continue
            fuel = p.get("fuel") == "Gas"
            rows.append({"key": f'pipeline:{p["project_id"]}',
                         "label": f'{"输气管线" if fuel else "输油管线"} · {p["name"]}'
                                  + (f' · {p["segment"]}' if p.get("segment") else ""),
                         "control": "map_show_gas" if fuel else "map_show_pipelines"})
    return sorted({row["key"]: row for row in rows}.values(), key=lambda row: row["label"])

def build_map_html(
    assets: list[dict[str, object]],
    ports: list[dict],
    chokepoints: list[dict],
    vessels: list[dict],
    day: str,
    chokepoint_day: str,
    *,
    visible_categories: set[str] | None = None,
    asset_popup,
    port_popup,
    chokepoint_popup,
    screenshot_requested: bool = False,
    pipelines: dict | None = None,
    snapshot_day: str | None = None,
    sea_day: str | None = None,
    vessel_tracks: dict | None = None,
    focus_request: dict | None = None,
) -> str:
    pipeline_features = []
    for feature in (pipelines or {}).get("features", []):
        if not feature["properties"].get("map_drawable", True):
            continue
        properties = {**feature["properties"], "popup": pipeline_catalog.popup(feature["properties"])}
        pipeline_features.append({**feature, "properties": properties})
    pipeline_json = json.dumps({"type": "FeatureCollection", "features": pipeline_features}, ensure_ascii=False).replace("</", "<\\/")
    markers = [
        {
            "lat": asset["map_lat"],
            "lon": asset["map_lon"],
            "popupKey": f'asset:{asset.get("country", "")}\x1f{asset["name"]}',
            "name": display_name(asset),
            "popup": asset_popup(asset),
        }
        for asset in assets
        if asset["map_drawable"] and not asset.get("map_is_proxy", False)
    ]
    marker_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    unlocated_json = json.dumps([
        {"lat": None, "lon": None,
         "popupKey": f'asset:{asset.get("country", "")}\x1f{asset["name"]}',
         "name": display_name(asset), "popup": asset_popup(asset)}
        for asset in assets if not asset.get("map_drawable") and asset.get("production_rows")
    ], ensure_ascii=False).replace("</", "<\\/")
    port_json = json.dumps([
        {"lat": port["lat"], "lon": port["lon"], "popupKey": f'port:{port["portid"]}',
         "name": display_name(port),
         "calls": port.get("portcalls"),
         "popup": port_popup(port, day)}
        for port in ports
    ], ensure_ascii=False).replace("</", "<\\/")
    chokepoint_json = json.dumps([
        {"lat": point["lat"], "lon": point["lon"],
         "popupKey": f'chokepoint:{point["portid"]}',
         "name": display_name(point),
         "calls": point.get("n_total"),
         "popup": chokepoint_popup(point, chokepoint_day)}
        for point in chokepoints
    ], ensure_ascii=False).replace("</", "<\\/")
    vessel_json = json.dumps([
        [
            vessel["lat"], vessel["lon"],
            vessel.get("name") or f'MMSI {vessel["mmsi"]}',
            vessel["mmsi"], vessel.get("region"),
            vessel.get("category_label"), vessel.get("imo"),
            vessel.get("sog"), vessel.get("course"),
            vessel.get("navigation_status"), vessel.get("call_sign"),
            destination_label(vessel), vessel.get("observed_at"),
            reception_time(vessel.get("received_at")),
            source_label(vessel),
            vessel.get("source_url") or AIS.SOURCE,
            vessel.get("source_attribution") or vessel.get("data_source") or "AIS数据来源",
            vessel.get("category", "unknown"),
            vessel.get("flag_country") or vessel.get("flag"),
            str(vessel.get("flag") or "").strip().upper() == "CN",
        ]
        for vessel in vessels
    ], ensure_ascii=False).replace("</", "<\\/")
    tracks_json = json.dumps(vessel_tracks or {}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    legend_lines = ["<b>图例</b>"]

    def legend_icon(shape: str, color: str) -> str:
        paths = {"asset": "M6 1 L11 6 L6 11 L1 6 Z",
                 "port": "M2 2 H10 V10 H2 Z",
                 "choke": "M3 1 H9 L12 6 L9 11 H3 L0 6 Z",
                 "vessel": "M6 0 L12 12 L6 9 L0 12 Z"}
        return f'<svg viewBox="0 0 12 12"><path d="{paths[shape]}" fill="{color}"/></svg>'

    categories = {"assets", "ports", "vessels"} if visible_categories is None else visible_categories
    location_items = []
    if "assets" in categories:
        location_items.append(f'<span>{legend_icon("asset", "#808080")}油气</span>')
    if "ports" in categories:
        location_items.extend([
            f'<span>{legend_icon("port", "#2563eb")}港口</span>',
            f'<span>{legend_icon("choke", "#7c3aed")}咽喉点</span>',
        ])
    if location_items:
        legend_lines.append('<div class="legend-row">' + "".join(location_items) + '</div>')
    pipeline_items = []
    for construction in (False, True):
        for fuel, color, label in (("Oil", "#8b2635", "输油管线"), ("Gas", "#416b86", "输气管线")):
            if any(f["properties"].get("fuel") == fuel for f in pipeline_features):
                dash = ' stroke-dasharray="9 5"' if construction else ""
                suffix = "（非运行）" if construction else ""
                pipeline_items.append(f'<span><svg viewBox="0 0 36 12" style="width:36px;height:12px"><path d="M0 6 H36" stroke="{color}" stroke-width="3"{dash}/></svg>{label}{suffix}</span>')
    if pipeline_items:
        legend_lines.append('<div class="legend-row">' + "".join(pipeline_items) + '</div>')
    if "vessels" in categories:
        legend_lines.append(
            '<div class="legend-row">'
            f'<span>{legend_icon("vessel", "#ef4444")}油轮/液货船</span>'
            f'<span>{legend_icon("vessel", "#2563eb")}货船</span>'
            f'<span>{legend_icon("vessel", "#64748b")}其他船舶/船型未知</span>'
            '</div>'
        )
    if not categories and not pipeline_features:
        legend_lines.append('<span>未选择显示类别</span>')
    legend_json = json.dumps("".join(legend_lines), ensure_ascii=False).replace("</", "<\\/")
    screenshot_date_json = json.dumps(snapshot_day or (day if day != "无数据" else chokepoint_day))
    vessel_times = [AIS.parse_utc(vessel.get("observed_at")) for vessel in vessels]
    latest_vessel_time = max((stamp for stamp in vessel_times if stamp is not None), default=None)
    vessel_time_label = latest_vessel_time.strftime("%Y-%m-%d %H:%M") if latest_vessel_time else "无数据"
    snapshot_label = f"历史观测日：{snapshot_day}\n海域监测日：{sea_day or '无数据'}\n" if snapshot_day else ""
    screenshot_label_json = json.dumps(
        snapshot_label + f"港口数据日：{day}\n咽喉点数据日：{chokepoint_day}\n船舶数据日：{vessel_time_label}",
        ensure_ascii=False)
    focus_json = json.dumps(focus_request or {}, ensure_ascii=False).replace("</", "<\\/")
    return compressed_document(f"""
    <!doctype html><html lang="zh-CN"><head>
    <meta charset="utf-8" />
    <style>{_MAP_STYLES}</style>
    <style>
      html, body, #map {{ height: 100%; margin: 0; }}
      #map {{ background: #e8eef4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      .leaflet-popup-content-wrapper {{ border-radius: 10px; box-shadow: 0 8px 24px rgba(15, 23, 42, .25); }}
      .leaflet-popup-content {{ margin: 13px 15px; min-width: 300px; max-width: 360px; }}
      .field-name {{ font-weight: 750; color: #0f172a; font-size: 14px; line-height: 1.35; margin-bottom: 3px; }}
      .country {{ color: #64748b; font-size: 14px; margin-bottom: 10px; }}
      .row {{ display: flex; justify-content: space-between; gap: 14px; padding: 5px 0; border-top: 1px solid #e2e8f0; font-size: 14px; }}
      .row span, .basis, .status {{ color: #64748b; }}
      .row strong {{ color: #0f172a; text-align: right; }}
      .map-detail .row span {{ flex: 0 0 96px; }}
      .map-detail .row strong {{ flex: 1; min-width: 0; overflow-wrap: anywhere; }}
      .asset-table-popup {{ width: 100%; max-width: 100%; box-sizing: border-box; }}
      .asset-table-popup .row {{ display: grid; grid-template-columns: 96px minmax(0, 1fr); }}
      .asset-table-popup .row strong {{ text-align: left; min-width: 0; overflow-wrap: anywhere; white-space: normal; }}
      .asset-table-popup a {{ display: block; max-width: 100%; word-break: break-all; }}
      .hierarchy-title {{ margin-top: 10px; padding-top: 8px; border-top: 2px solid #cbd5e1; color: #334155; font-size: 14px; font-weight: 700; }}
      .level-metric {{ padding: 7px 8px; margin-top: 6px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 7px; }}
      .level-head, .output-line {{ display: flex; justify-content: space-between; gap: 10px; font-size: 14px; }}
      .level-head span, .output-line span, .metric-detail {{ color: #64748b; }}
      .level-head b {{ color: #334155; text-align: right; }}
      .output-line {{ margin-top: 4px; align-items: baseline; }}
      .output-line strong {{ color: #991b1b; font-size: 14px; }}
      .metric-detail, .other-metric {{ font-size: 14px; margin-top: 2px; line-height: 1.35; }}
      .other-metric {{ color: #92400e; }}
      .mix-row {{ display: grid; grid-template-columns: 90px 1fr 110px; gap: 8px; align-items: center; margin-top: 6px; font-size: 14px; }}
      .mix-row span {{ color: #475569; }}
      .mix-row b {{ color: #334155; text-align: right; font-weight: 600; }}
      .port-popup .row span, .port-popup .mix-row span, .port-popup .mix-row b {{ color: #0f172a; }}
      .port-popup .mix-row {{ grid-template-columns: 84px minmax(40px, 1fr) 140px; }}
      .mix-track {{ height: 6px; border-radius: 999px; background: #e2e8f0; overflow: hidden; }}
      .mix-track i {{ display: block; height: 100%; border-radius: 999px; }}
      .status, .basis {{ font-size: 14px; margin-top: 8px; line-height: 1.4; }}
      .source {{ display: block; color: #2563eb; font-size: 14px; margin-top: 8px; text-decoration: none; }}
      .map-legend {{ background: rgba(255,255,255,.95); padding: 9px 11px; border-radius: 8px; box-shadow: 0 2px 10px rgba(15,23,42,.15); color: #0f172a; font-size: 14px; line-height: 1.45; }}
      .map-legend b {{ font-size: 14px; }}
      .map-legend .legend-row {{ display: flex; gap: 14px; margin-top: 4px; }}
      .map-legend .legend-row {{ flex-wrap: wrap; }}
      .map-legend {{ max-width: calc(100vw - 40px); box-sizing: border-box; }}
      .map-detail {{ width: min(410px, calc(100vw - 40px)); }}
      .map-detail > .leaflet-popup {{ position: relative !important; transform: none !important; left: 0 !important; bottom: auto !important; margin: 0 !important; width: 100%; }}
      .map-detail .leaflet-popup-tip-container {{ display: none; }}
      .map-detail .leaflet-popup-content {{ min-width: 0; max-width: 100%; max-height: min(420px, calc(100vh - 250px)); overflow: auto; }}
      .map-legend span {{ white-space: nowrap; }}
      .map-legend svg {{ display: inline-block; width: 10px; height: 10px; margin-right: 6px; vertical-align: -1px; }}
      .map-date {{ background: rgba(255,255,255,.96); padding: 7px 9px; border-radius: 7px; box-shadow: 0 2px 10px #0f172a26; color: #172b4d; font-size: 14px; max-width: calc(100vw - 40px); box-sizing: border-box; }}
      .map-date {{ white-space: pre-line; line-height: 1.6; }}
      .asset-icon, .port-icon, .chokepoint-icon, .vessel-icon, .vessel-cluster {{ background: transparent; border: 0; }}
      .asset-icon svg, .port-icon svg, .chokepoint-icon svg, .vessel-icon svg, .vessel-cluster svg {{ display: block; filter: drop-shadow(0 1px 1px rgba(15,23,42,.45)); }}
      .leaflet-tooltip {{ border: 0; border-radius: 7px; padding: 5px 8px; box-shadow: 0 3px 12px rgba(15,23,42,.18); font-size: 14px; }}
      .leaflet-control-attribution, .leaflet-control-attribution a {{ color: #6b7280; font-size: 11px; }}
      .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {{ background: transparent; }}
      .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {{ background: #808080; color: white; font-weight: 700; border-radius: 7px; transform: rotate(45deg); box-shadow: 0 0 0 5px rgba(128,128,128,.22); }}
      .pipeline-path:focus {{ outline: none; }}
      .pipeline-path:focus-visible {{ stroke-width: 5; stroke-opacity: 1; }}
      .marker-cluster-small span, .marker-cluster-medium span, .marker-cluster-large span {{ display: block; transform: rotate(-45deg); }}
      .map-tools {{ background: rgba(255,255,255,.96); border-radius: 8px; padding: 8px 10px; color: #172b4d; box-shadow: 0 2px 10px #0f172a26; }}
      .map-tools button {{ background: #0e5570; color: white; border: 0; border-radius: 5px; padding: 8px 12px; cursor: pointer; font-size: 14px; }}
      .map-tools button:disabled {{ opacity: .6; cursor: wait; }}
      .map-tools span {{ display: block; max-width: 280px; font-size: 14px; margin-top: 4px; }}
      .map-tools span:empty {{ display: none; }}
    </style></head><body><div id="map"></div>
    <script>{_MAP_SCRIPTS}</script>
    <script>
      const map = L.map('map', {{zoomControl: true}}).setView([25.5, 48.5], 4);
      const screenshotDate = {screenshot_date_json};
      const legend = L.control({{position: 'topright'}});
      legend.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-legend');
        el.innerHTML = {legend_json};
        return el;
      }};
      legend.addTo(map);
      L.Popup.mergeOptions({{autoPan: false}});
      const detailControl = L.control({{position: 'topright'}});
      detailControl.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-detail');
        el.style.display = 'none';
        L.DomEvent.disableClickPropagation(el);
        L.DomEvent.disableScrollPropagation(el);
        return el;
      }};
      detailControl.addTo(map);
      const dateControl = L.control({{position: 'bottomleft'}});
      dateControl.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-date');
        el.textContent = {screenshot_label_json};
        return el;
      }};
      dateControl.addTo(map);
      const assets = {marker_json};
      const unlocatedAssets = {unlocated_json};
      const ports = {port_json};
      const chokepoints = {chokepoint_json};
      const vessels = {vessel_json};
      const pipelines = {pipeline_json};
      const focusRequest = {focus_json};
      const popupStateKey = 'energy-map-popup-v1';
      const markerByPopupKey = new Map();
      const clusterByPopupKey = new Map();
      map.on('popupopen', (event) => {{
        const el = detailControl.getContainer();
        el.style.display = '';
        el.replaceChildren(event.popup.getElement());
        const key = event.popup?._source?.options?.popupKey || event.popup.options.popupKey;
        if (key) {{ try {{ sessionStorage.setItem(popupStateKey, key); }} catch (error) {{ }} }}
      }});
      map.on('popupclose', (event) => {{
        detailControl.getContainer().style.display = 'none';
        const key = event.popup?._source?.options?.popupKey || event.popup.options.popupKey;
        try {{ if (key && sessionStorage.getItem(popupStateKey) === key) sessionStorage.removeItem(popupStateKey); }}
        catch (error) {{ }}
      }});
      const escapeHTML = (value) => String(value ?? '—').replace(/[&<>"']/g, (char) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }}[char]));
      const shown = (value, suffix = '') => value == null || value === ''
        ? '—' : `${{escapeHTML(value)}}${{suffix}}`;
      const vesselPopup = (vessel) => {{
        const name = vessel[2], region = vessel[4], navigationStatus = vessel[9],
          destination = vessel[11], receivedAt = vessel[13], dataSource = vessel[14],
          flagCountry = vessel[18];
        return `<div class="popup-card">
          <div class="row"><span>船名</span><strong>${{shown(name)}}</strong></div>
          <div class="row"><span>当前地点</span><strong>${{shown(region)}}</strong></div>
          <div class="row"><span>船籍</span><strong>${{shown(flagCountry)}}</strong></div>
          <div class="row"><span>航行状态</span><strong>${{shown(navigationStatus)}}</strong></div>
          <div class="row"><span>目的地</span><strong>${{shown(destination)}}</strong></div>
          <div class="row"><span>接收时间</span><strong>${{shown(receivedAt)}}</strong></div>
          <div class="row"><span>数据源</span><strong>${{shown(dataSource)}}</strong></div>
        </div>`;
      }};
      const allPoints = ports.map((p) => [p.lat, p.lon])
        .concat(chokepoints.map((p) => [p.lat, p.lon]))
        .concat(assets.map((a) => [a.lat, a.lon]))
        .concat(vessels.map((v) => [v[0], v[1]]));
      if (allPoints.length) {{
        map.fitBounds(L.latLngBounds(allPoints), {{padding: [36, 36], maxZoom: 5, animate: false}});
      }}
      // Preserve the user's map view across Streamlit reruns.
      const viewKey = 'energy-map-view-v2';
      try {{
        const saved = JSON.parse(sessionStorage.getItem(viewKey));
        if (saved && Array.isArray(saved.center) && Number.isFinite(saved.zoom)) {{
          map.setView(saved.center, saved.zoom, {{animate: false}});
        }}
      }} catch (error) {{ /* Storage can be disabled by the embedding browser. */ }}
      map.on('moveend', () => {{
        try {{ sessionStorage.setItem(viewKey, JSON.stringify({{
          center: [map.getCenter().lat, map.getCenter().lng], zoom: map.getZoom()
        }})); }} catch (error) {{ }}
      }});
      // Request tiles only for the final initial viewport.
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: '地图来源：<a href="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer" target="_blank" rel="noopener">Esri World Street Map</a> &copy; Esri 及数据提供方',
        maxZoom: 18, crossOrigin: true
      }}).addTo(map);
      const assetLayer = L.markerClusterGroup({{showCoverageOnHover: false, maxClusterRadius: 34,
          disableClusteringAtZoom: 8, spiderfyOnMaxZoom: true}}).addTo(map);
      const portLayer = L.layerGroup().addTo(map);
      const chokepointLayer = L.layerGroup().addTo(map);
      map.createPane('pipelinePane');
      map.getPane('pipelinePane').style.zIndex = 350;
      const pipelineStyle = (feature) => {{
        const p = feature.properties;
        const operating = p.status === 'operating';
        return {{color: p.fuel === 'Gas' ? '#416b86' : '#8b2635',
          weight: 3, opacity: operating ? .95 : .75,
          dashArray: operating ? null : '9 5'}};
      }};
      const pipelineLayer = L.geoJSON(pipelines, {{
        pane: 'pipelinePane', className: 'pipeline-path', style: pipelineStyle,
        onEachFeature: (feature, layer) => {{
          const p = feature.properties;
          layer.options.popupKey = `pipeline:${{p.project_id}}`;
          layer.bindTooltip(escapeHTML(p.name + (p.segment ? ' · ' + p.segment : '')), {{sticky: true}})
            .bindPopup(p.popup, {{maxWidth: 410}});
          layer.on('mouseover', () => layer.setStyle({{weight: 5, opacity: 1}}));
          layer.on('mouseout', () => pipelineLayer.resetStyle(layer));
          markerByPopupKey.set(layer.options.popupKey, layer);
        }}
      }}).addTo(map);
      const vesselLayer = L.markerClusterGroup({{
        showCoverageOnHover: false, maxClusterRadius: 24, disableClusteringAtZoom: 7,
        spiderfyOnMaxZoom: true, animate: false,
        chunkedLoading: true, chunkInterval: 20, chunkDelay: 10,
        iconCreateFunction: (cluster) => {{
          const count = cluster.getChildCount();
          const hasChineseFlag = cluster.getAllChildMarkers().some(marker => marker.options.chineseFlag);
          const label = count > 999 ? `${{Math.round(count / 100) / 10}}k` : String(count);
          return L.divIcon({{
            className: 'vessel-cluster', iconSize: [38, 34], iconAnchor: [19, 17],
            html: `<svg width="38" height="34" viewBox="0 0 38 34">
              <path d="M19 1 L37 32 L19 26 L1 32 Z" fill="${{hasChineseFlag ? '#334155' : '#94a3b8'}}"
                stroke="${{hasChineseFlag ? '#dc2626' : '#ffffff'}}" stroke-width="${{hasChineseFlag ? 2.2 : 1.4}}"/>
              <text x="19" y="22" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">${{label}}</text>
            </svg>`
          }});
        }}
      }}).addTo(map);
      assets.forEach((asset) => {{
        const size = 18;
        const icon = L.divIcon({{
          className: 'asset-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
            <polygon points="${{size/2}},1 ${{size-1}},${{size/2}} ${{size/2}},${{size-1}} 1,${{size/2}}"
              fill="#808080" fill-opacity="1" stroke="#666666"
              stroke-width="1.5"/>
          </svg>`
        }});
        const marker = L.marker([asset.lat, asset.lon], {{icon, popupKey: asset.popupKey}})
          .bindTooltip(asset.name, {{direction: 'top', opacity: .95}})
          .bindPopup(asset.popup, {{maxWidth: 390}}).addTo(assetLayer);
        markerByPopupKey.set(asset.popupKey, marker);
        clusterByPopupKey.set(asset.popupKey, assetLayer);
      }});
      ports.forEach((port) => {{
        if (port.lat == null || port.lon == null) return;
        const size = 16;
        const icon = L.divIcon({{
          className: 'port-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
            <rect x="1.5" y="1.5" width="${{size-3}}" height="${{size-3}}" rx="2.5"
              fill="#2563eb" fill-opacity=".9" stroke="#ffffff" stroke-width="1.5"/>
          </svg>`
        }});
        const label = document.createElement('div');
        label.textContent = `${{port.name}} · ${{port.calls == null ? '无日度记录' : port.calls + ' 艘次进港'}}`;
        const marker = L.marker([port.lat, port.lon], {{icon, popupKey: port.popupKey}})
          .bindTooltip(label, {{direction: 'top', opacity: .95}})
          .bindPopup(port.popup, {{maxWidth: 410, autoPanPaddingTopLeft: [10, 135], autoPanPaddingBottomRight: [10, 10]}}).addTo(portLayer);
        markerByPopupKey.set(port.popupKey, marker);
      }});
      chokepoints.forEach((point) => {{
        const size = 22;
        const icon = L.divIcon({{
          className: 'chokepoint-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 24 24">
            <polygon points="6,2 18,2 23,12 18,22 6,22 1,12"
              fill="#7c3aed" fill-opacity=".94" stroke="#ffffff" stroke-width="1.5"/>
          </svg>`
        }});
        const label = document.createElement('div');
        label.textContent = `${{point.name}} · ${{point.calls == null ? '无日度记录' : point.calls + ' 艘通过'}}`;
        const marker = L.marker([point.lat, point.lon], {{icon, popupKey: point.popupKey}})
          .bindTooltip(label, {{direction: 'top', opacity: .95, permanent: true}})
          .bindPopup(point.popup, {{maxWidth: 410}}).addTo(chokepointLayer);
        markerByPopupKey.set(point.popupKey, marker);
      }});
      const vesselColors = {{
        tanker: '#ef4444', cargo: '#2563eb', other: '#64748b'
      }};
      const mutedVesselColors = {{
        tanker: '#fca5a5', cargo: '#a5b4fc', other: '#cbd5e1'
      }};
      const vesselTracks = {tracks_json};
      map.createPane('vesselTrackPane');
      map.getPane('vesselTrackPane').style.zIndex = 450;
      const vesselTrackLayer = L.layerGroup().addTo(map);
      let activeTrackMmsi = null;
      const showVesselTrack = (mmsi, color) => {{
        vesselTrackLayer.clearLayers();
        activeTrackMmsi = String(mmsi);
        const points = vesselTracks[activeTrackMmsi] || [];
        if (points.length < 2) return;
        L.polyline(points.map(p => [p[0], p[1]]), {{pane: 'vesselTrackPane',
          color, weight: 3, opacity: .95, dashArray: '6 6', interactive: false}}).addTo(vesselTrackLayer);
        L.circleMarker([points[0][0], points[0][1]], {{pane: 'vesselTrackPane',
          radius: 4, color, fillColor: color, fillOpacity: 1, weight: 2}})
          .bindTooltip(escapeHTML(`起点 · ${{points[0][2]}}`)).addTo(vesselTrackLayer);
      }};
      const vesselMarkers = vessels.map((vessel) => {{
        const [lat, lon, name, mmsi, region, categoryLabel, imo, sog, course,
          navigationStatus, callSign, destination, observedAt, receivedAt,
          dataSource, sourceUrl, attribution, category, flagCountry, chineseFlag] = vessel;
        const palette = chineseFlag ? vesselColors : mutedVesselColors;
        const color = palette[category] || palette.other;
        const angle = Number.isFinite(Number(course)) ? Number(course) : 0;
        const icon = L.divIcon({{
          className: 'vessel-icon', iconSize: [18, 18], iconAnchor: [9, 9],
          html: `<svg width="18" height="18" viewBox="0 0 18 18" style="transform:rotate(${{angle}}deg)">
            <path d="M9 1 L16 16 L9 12.8 L2 16 Z" fill="${{color}}"
              stroke="${{chineseFlag ? '#dc2626' : '#ffffff'}}" stroke-width="${{chineseFlag ? 2.2 : 1.15}}"/>
          </svg>`
        }});
        const marker = L.marker([lat, lon], {{icon, chineseFlag, zIndexOffset: chineseFlag ? 500 : 0}});
        marker.options.popupKey = `vessel:${{mmsi}}`;
        marker.bindTooltip(escapeHTML(name), {{direction: 'top', opacity: .95}})
          .bindPopup(() => vesselPopup(vessel), {{maxWidth: 410}});
        marker.on('popupopen', () => showVesselTrack(mmsi, color));
        marker.on('popupclose', () => {{
          if (activeTrackMmsi === String(mmsi)) {{vesselTrackLayer.clearLayers();activeTrackMmsi=null;}}
        }});
        markerByPopupKey.set(marker.options.popupKey, marker);
        clusterByPopupKey.set(marker.options.popupKey, vesselLayer);
        return marker;
      }});
      // A single bulk update avoids reclustering and rewriting DOM per ship.
      vesselLayer.addLayers(vesselMarkers);
      const focusObject = (key, locate = true) => {{
        const marker = markerByPopupKey.get(key);
        if (marker) {{
          const cluster = clusterByPopupKey.get(key);
          if (locate) {{
            if (marker.getBounds) map.fitBounds(marker.getBounds(), {{maxZoom: 9, padding: [30, 30]}});
            else if (marker.getLatLng) map.setView(marker.getLatLng(), Math.max(map.getZoom(), 9), {{animate: false}});
          }}
          if (cluster) cluster.zoomToShowLayer(marker, () => marker.openPopup());
          else marker.openPopup();
          return true;
        }}
        // No marker or coordinates are created for an unlocated record. The
        // popup is moved into the fixed detail control, as for unlocated ports.
        const record = [...ports, ...unlocatedAssets].find(row => row.popupKey === key && (row.lat == null || row.lon == null));
        if (record) {{
          L.popup({{popupKey: key, maxWidth: 410, autoPan: false}})
            .setLatLng(map.getCenter()).setContent(record.popup).openOn(map);
          return true;
        }}
        return false;
      }};
      const focusToken = `${{focusRequest.revision}}:${{focusRequest.key}}`;
      let lastFocus = null;
      try {{ lastFocus = sessionStorage.getItem('energy-map-focus-v1'); }} catch (error) {{ }}
      if (focusRequest.key && lastFocus !== focusToken && focusObject(focusRequest.key)) {{
        try {{ sessionStorage.setItem('energy-map-focus-v1', focusToken); }} catch (error) {{ }}
      }} else {{
        try {{
          const savedPopupKey = sessionStorage.getItem(popupStateKey);
          if (savedPopupKey) focusObject(savedPopupKey, false);
        }} catch (error) {{ }}
      }}
      {map_tools.SCREENSHOT_SCRIPT}
      if ({str(screenshot_requested).lower()}) {{
        setTimeout(() => window.saveMapPng(), 800);
      }}
    </script></body></html>
    """)
