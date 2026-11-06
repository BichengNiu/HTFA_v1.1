"""Build a source-dated, print-ready report from the map's current data."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import htfa.monitoring.energy_supply.processing.monitoring_cards as monitoring_cards
from htfa.monitoring.energy_supply.contracts.records import latest_by_node
from htfa.monitoring.energy_supply.processing.entity_names import display_name

from . import card_html

COLORS = ("#1769aa", "#d97706", "#7c3aed", "#14866d", "#dc4b4b", "#64748b")


def _esc(value: object) -> str:
    return escape(str(value if value not in (None, "") else "—"), quote=True)


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _display_date(value: object) -> str:
    day = _date(value)
    return day.isoformat() if day else "无可用记录"


def _fmt(value: object, digits: int = 0) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{number:,.{digits}f}"


def _section(title: str, body: str, page: bool = False) -> str:
    cls = "report-page" if page else "report-cover"
    return f'<section class="{cls}"><h2>{_esc(title)}</h2>{body}</section>'


def _table(
    headers: list[str], rows: list[list[object]], empty: str = "当前范围没有可用记录"
) -> str:
    if not rows:
        return f'<p class="empty">{_esc(empty)}</p>'
    head = "".join(f"<th>{_esc(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _metric_cards(cards: list[tuple[str, str, str]], *, show_notes: bool = True) -> str:
    return (
        '<div class="metric-grid">'
        + "".join(
            f'<div class="metric-card"><span>{_esc(label)}</span><strong>{_esc(value)}</strong>'
            f"{f'<small>{_esc(note)}</small>' if show_notes else ''}</div>"
            for label, value, note in cards
        )
        + "</div>"
    )


def _time_series_chart(
    title: str, series: list[tuple[str, list[tuple[object, object]]]], unit: str = ""
) -> str:
    parsed: dict[str, dict[date, float | None]] = {}
    all_dates: set[date] = set()
    for label, pairs in series:
        values: dict[date, float | None] = {}
        for raw_day, raw_value in pairs:
            day = _date(raw_day)
            if day is None:
                continue
            values[day] = _number(raw_value)
            all_dates.add(day)
        parsed[label] = values
    if not all_dates:
        return f'<div class="chart-card"><h3>{_esc(title)}</h3><p class="empty">历史记录不可用</p></div>'

    dates = sorted(all_dates)
    valid_values = [
        value
        for values in parsed.values()
        for value in values.values()
        if value is not None
    ]
    maximum = max(valid_values, default=1.0)
    y_max = max(maximum * 1.12, 1.0)
    tick_count = min(6, max(2, len(dates)))
    label_indexes = sorted(
        {
            round(index * (len(dates) - 1) / (tick_count - 1))
            for index in range(tick_count)
        }
    )
    pieces = [
        f'<div class="chart-card"><h3>{_esc(title)}</h3>',
        '<div class="chart-legend">',
    ]
    pieces.extend(
        f'<span><i style="background:{COLORS[index % len(COLORS)]}"></i>{_esc(label)}</span>'
        for index, label in enumerate(parsed)
    )
    pieces.append(
        f'</div><small class="chart-scale">纵轴范围：0–{_fmt(y_max, 1)} {_esc(unit)}</small>'
        '<div class="chart-series">'
    )
    for index, (label, values) in enumerate(parsed.items()):
        color = COLORS[index % len(COLORS)]
        pieces.append(
            f'<div class="chart-series-row"><span class="chart-series-label">{_esc(label)}</span>'
        )
        pieces.append(
            '<div class="chart-bars" role="img" aria-label="' + _esc(label) + '">'
        )
        for day in dates:
            value = values.get(day)
            if value is None:
                pieces.append(
                    f'<span class="chart-bar missing" title="{day.isoformat()}：无记录"></span>'
                )
                continue
            bar_height = max(1.0, min(100.0, value / y_max * 100))
            pieces.append(
                f'<span class="chart-bar" style="height:{bar_height:.2f}%;background:{color}" '
                f'title="{day.isoformat()}：{_fmt(value, 1)}"></span>'
            )
        pieces.append("</div></div>")
    pieces.append('</div><div class="chart-date-labels">')
    pieces.extend(
        f"<span>{dates[index].strftime('%m-%d')}</span>" for index in label_indexes
    )
    pieces.append(
        f'</div><small class="unit">{_esc(unit)} · 按同一量程展示；日期按 UTC，缺报保留为空</small></div>'
    )
    return "".join(pieces)


def _history_by_node(rows: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        result[str(row.get("portid", ""))].append(row)
    for values in result.values():
        values.sort(key=lambda item: str(item.get("date", "")))
    return result


def _aggregate(
    rows: list[dict], metric: str, scale: float = 1.0
) -> tuple[list[tuple[str, object]], dict[str, int]]:
    values: dict[str, list[float]] = defaultdict(list)
    dates = set()
    for row in rows:
        day = _date(row.get("date"))
        if day is not None:
            dates.add(day)
        number = _number(row.get(metric))
        if day is not None and number is not None:
            values[day.isoformat()].append(number / scale)
    output = [
        (
            day.isoformat(),
            sum(values[day.isoformat()]) if values.get(day.isoformat()) else None,
        )
        for day in sorted(dates)
    ]
    coverage = {day: len(numbers) for day, numbers in values.items()}
    return output, coverage


def _window_mean(
    by_date: dict[date, dict], end: date, days: int, metric: str
) -> float | None:
    values: list[float] = []
    for offset in range(days):
        row = by_date.get(end - timedelta(days=offset))
        number = _number(row.get(metric)) if row else None
        if number is None:
            return None
        values.append(number)
    return sum(values) / days


def _change_table(
    choke_rows: list[dict], choke_catalog: list[dict], latest_day: object
) -> str:
    catalog = {str(row.get("portid")): row for row in choke_catalog}
    by_node: dict[str, dict[date, dict]] = defaultdict(dict)
    for row in choke_rows:
        day = _date(row.get("date"))
        if day:
            by_node[str(row.get("portid"))][day] = row
    rows: list[list[object]] = []
    for point_id, point_rows in by_node.items():
        if not point_rows:
            continue
        end = _date(latest_day) or max(point_rows)
        if end not in point_rows:
            end = max(point_rows)
        current = _window_mean(point_rows, end, 7, "n_total")
        previous = _window_mean(point_rows, end - timedelta(days=7), 7, "n_total")
        if current is None or previous is None or previous == 0:
            delta: object = "窗口记录不完整或基期为0"
        else:
            delta = f"{(current / previous - 1) * 100:+.1f}%"
        point = catalog.get(point_id, {})
        rows.append(
            [
                display_name(point),
                end.isoformat(),
                _fmt(previous, 1),
                _fmt(current, 1),
                delta,
            ]
        )
    return _table(
        [
            "咽喉点",
            "节点最新日",
            "前7日均值（艘次/日）",
            "最近7日均值（艘次/日）",
            "环比变化",
        ],
        rows,
    )


def _mercator_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat = min(85.05112878, max(-85.05112878, lat))
    scale = 256 * (2**zoom)
    x = (lon + 180) / 360 * scale
    sine = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sine) / (1 - sine)) / (4 * math.pi)) * scale
    return x, y


def _basemap_tiles(
    lon_min: float, lon_max: float, lat_min: float, lat_max: float
) -> str:
    """Place the same Esri street-map tiles as the interactive map in print HTML."""
    zoom = 5
    left, bottom = _mercator_pixel(lat_min, lon_min, zoom)
    right, top = _mercator_pixel(lat_max, lon_max, zoom)
    width, height = right - left, bottom - top
    first_x, last_x = math.floor(left / 256), math.floor((right - 1) / 256)
    first_y, last_y = math.floor(top / 256), math.floor((bottom - 1) / 256)
    tiles = []
    for tile_y in range(first_y, last_y + 1):
        for tile_x in range(first_x, last_x + 1):
            x = (tile_x * 256 - left) / width * 100
            y = (tile_y * 256 - top) / height * 100
            tile_width = 256 / width * 100
            tile_height = 256 / height * 100
            tiles.append(
                f'<img class="map-tile" loading="eager" alt="" '
                f'src="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/'
                f'MapServer/tile/{zoom}/{tile_y}/{tile_x}" '
                f'style="left:{x:.4f}%;top:{y:.4f}%;width:{tile_width:.4f}%;'
                f'height:{tile_height:.4f}%">'
            )
    return "".join(tiles)


def _overview_map(
    ports: list[dict],
    chokes: list[dict],
    assets: list[dict],
    regions: dict[str, tuple[float, float, float, float]],
    vessels: list[dict] | None = None,
    include_basemap: bool = False,
) -> str:
    coordinates = []
    for row in ports + chokes + (vessels or []):
        coordinates.append((_number(row.get("lat")), _number(row.get("lon"))))
    for asset in assets:
        if asset.get("map_drawable", True):
            coordinates.append(
                (
                    _number(asset.get("map_lat", asset.get("lat"))),
                    _number(asset.get("map_lon", asset.get("lon"))),
                )
            )
    for south, north, west, east in regions.values():
        coordinates.extend(((south, west), (north, east)))
    coordinates = [
        (lat, lon) for lat, lon in coordinates if lat is not None and lon is not None
    ]
    if coordinates:
        lat_min, lat_max = (
            min(lat for lat, _ in coordinates),
            max(lat for lat, _ in coordinates),
        )
        lon_min, lon_max = (
            min(lon for _, lon in coordinates),
            max(lon for _, lon in coordinates),
        )
        lat_padding = max(0.5, (lat_max - lat_min) * 0.05)
        lon_padding = max(0.5, (lon_max - lon_min) * 0.05)
        lat_min, lat_max = lat_min - lat_padding, lat_max + lat_padding
        lon_min, lon_max = lon_min - lon_padding, lon_max + lon_padding
    else:
        lon_min, lon_max, lat_min, lat_max = 29.0, 64.0, 8.0, 34.0
    lat_min = min(85.0, max(-85.0, lat_min))
    lat_max = min(85.0, max(-85.0, lat_max))
    # The cover map is printed on an A4 portrait page. Expand its longitude
    # bounds to make a landscape frame while preserving the projected geometry.
    if include_basemap:
        vertical_span = math.log(
            math.tan(math.pi / 4 + math.radians(lat_max) / 2)
        ) - math.log(math.tan(math.pi / 4 + math.radians(lat_min) / 2))
        target_lon_span = math.degrees(vertical_span * 1.65)
        if lon_max - lon_min < target_lon_span:
            center = (lon_min + lon_max) / 2
            lon_min, lon_max = (
                center - target_lon_span / 2,
                center + target_lon_span / 2,
            )
    lon_span = lon_max - lon_min
    mercator_top = math.log(math.tan(math.pi / 4 + math.radians(lat_max) / 2))
    mercator_bottom = math.log(math.tan(math.pi / 4 + math.radians(lat_min) / 2))
    mercator_span = mercator_top - mercator_bottom
    aspect = math.radians(lon_span) / mercator_span

    def xy(lat: object, lon: object) -> tuple[float, float] | None:
        yv, xv = _number(lat), _number(lon)
        if (
            yv is None
            or xv is None
            or not (lat_min <= yv <= lat_max and lon_min <= xv <= lon_max)
        ):
            return None
        yv = min(85.0, max(-85.0, yv))
        projected_y = math.log(math.tan(math.pi / 4 + math.radians(yv) / 2))
        return (
            (xv - lon_min) / lon_span * 100,
            (mercator_top - projected_y) / mercator_span * 100,
        )

    parts = [
        f'<div class="overview-map" role="img" aria-label="监测水域地图与监测对象位置" '
        f'style="aspect-ratio:{aspect:.4f}/1"><div class="overview-map-plot">'
    ]
    if include_basemap:
        parts.append(_basemap_tiles(lon_min, lon_max, lat_min, lat_max))
    choke_leaders = []
    choke_labels = []
    for choke in chokes:
        point = xy(choke.get("lat"), choke.get("lon"))
        if not point:
            continue
        x, y = point
        name = display_name(choke)
        point_id = str(choke.get("portid", ""))
        dx, dy, align = {
            "chokepoint1": (5.5, -5.0, "left"),  # 苏伊士
            "chokepoint4": (4.5, -7.0, "left"),  # 曼德
            "chokepoint6": (-4.5, -5.5, "right"),  # 霍尔木兹
        }.get(point_id, (5.0 if x < 58 else -5.0, -6.0, "left" if x < 58 else "right"))
        elbow_x, elbow_y = x + dx * 0.55, y + dy * 0.35
        end_x, end_y = x + dx, y + dy
        choke_leaders.append(
            f'<path d="M {x * 10:.2f} {y * 10:.2f} L {elbow_x * 10:.2f} {elbow_y * 10:.2f} '
            f'L {end_x * 10:.2f} {end_y * 10:.2f}"/>'
        )
        choke_labels.append(
            f'<span class="choke-label {align}" style="left:{end_x:.3f}%;top:{end_y:.3f}%">'
            f"{_esc(name)}</span>"
        )
    if choke_leaders:
        parts.append(
            '<svg class="choke-leaders" viewBox="0 0 1000 1000" preserveAspectRatio="none" '
            'aria-hidden="true">' + "".join(choke_leaders) + "</svg>"
        )

    def append_point(
        kind: str, label: object, lat: object, lon: object, count: int = 1
    ) -> None:
        point = xy(lat, lon)
        if point:
            x, y = point
            title = f"{count} 艘 AIS 船位" if kind == "vessel" else str(label)
            parts.append(
                f'<span class="map-point {kind}" title="{_esc(title)}" '
                f'style="left:{x:.3f}%;top:{y:.3f}%"></span>'
            )

    for port in ports:
        append_point("port", display_name(port), port.get("lat"), port.get("lon"))
    for asset in assets:
        if not asset.get("map_drawable", True):
            continue
        append_point(
            "asset",
            display_name(asset),
            asset.get("map_lat", asset.get("lat")),
            asset.get("map_lon", asset.get("lon")),
        )
    for choke in chokes:
        append_point("choke", display_name(choke), choke.get("lat"), choke.get("lon"))
    parts.extend(choke_labels)

    vessel_cells: dict[tuple[int, int], list[float | int]] = {}
    for vessel in vessels or []:
        point = xy(vessel.get("lat"), vessel.get("lon"))
        if point:
            x, y = point
            cell = (math.floor(x / 4), math.floor(y / 5))
            bucket = vessel_cells.setdefault(cell, [0, 0.0, 0.0])
            bucket[0] += 1
            bucket[1] += x
            bucket[2] += y
    for count, x_sum, y_sum in vessel_cells.values():
        avg_x, avg_y = x_sum / count, y_sum / count
        projected_y = mercator_top - avg_y / 100 * mercator_span
        avg_lat = math.degrees(2 * math.atan(math.exp(projected_y)) - math.pi / 2)
        avg_lon = lon_min + avg_x / 100 * lon_span
        append_point("vessel", "AIS船位", avg_lat, avg_lon, count=int(count))

    parts.append("</div></div>")
    return "".join(parts)


def _distribution(vessels: list[dict]) -> str:
    if not vessels:
        return '<p class="empty">当前快照没有可用船位；这不表示监测水域内没有船舶。</p>'
    region_counts = Counter(str(v.get("region") or "水域未知") for v in vessels)
    type_counts = Counter(str(v.get("category_label") or "船型待识别") for v in vessels)
    rows = [[label, count] for label, count in region_counts.most_common()]
    type_rows = [[label, count] for label, count in type_counts.most_common()]
    return (
        '<div class="chart-grid"><div><h3>水域分布</h3>'
        + _table(["监测水域", "快照船位数"], rows)
        + "</div><div><h3>船型分布</h3>"
        + _table(["船型", "快照船位数"], type_rows)
        + "</div></div>"
    )


def build_report_html(
    *,
    scope_label: str,
    generated_at: datetime | None,
    port_catalog: list[dict],
    choke_catalog: list[dict],
    latest_ports: list[dict],
    port_history: list[dict],
    choke_history: list[dict],
    assets: list[dict],
    asset_table: list[dict],
    vessels: list[dict],
    regions: dict[str, tuple[float, float, float, float]],
    port_day: object,
    choke_day: object,
    ais_status: str,
    ais_source_note: str,
    errors: list[str] | None = None,
    monitoring_summary_cards: list | None = None,
) -> str:
    """Return self-contained HTML for browser preview and print/PDF."""
    timestamp = generated_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    timestamp = timestamp.astimezone(ZoneInfo("Asia/Shanghai"))
    # Supplementary WPI/industry entries are map-only unless the catalog
    # explicitly marks them as independent PortWatch statistics.
    stat_ports = [p for p in port_catalog if p.get("statistics_available", False)]
    dated_calls = [p for p in latest_ports if _number(p.get("portcalls")) is not None]
    catalog_chokes = len(choke_catalog)
    report_assets = list(assets)
    map_html = _overview_map(
        port_catalog,
        choke_catalog,
        report_assets,
        regions,
        vessels,
        include_basemap=True,
    )
    cover_cards = card_html.cards_html(
        monitoring_summary_cards
        or monitoring_cards.build_cards(
            port_catalog,
            choke_catalog,
            port_history,
            choke_history,
            _date(port_day),
            _date(choke_day),
            vessel_day=timestamp.date(),
            assets=report_assets,
        )
    )
    cover_table = _table(
        ["数据", "源站观测日 / 状态", "说明"],
        [
            [
                "PortWatch 港口",
                _display_date(port_day),
                f"所选报告范围内 {len(dated_calls)}/{len(latest_ports)} 个点位有当日记录",
            ],
            [
                "PortWatch 咽喉点",
                _display_date(choke_day),
                f"纳入 {catalog_chokes} 个节点",
            ],
            ["AIS 船位", ais_status, ais_source_note],
            ["油气资产", "逐项列示披露日期", "静态公开披露；不视为实时遥测"],
        ],
    )
    overview = (
        '<div class="report-masthead">'
        + '<span class="report-sponsor">中国驻阿联酋大使馆、国家发改委国家信息中心</span>'
        + f'<span class="report-generated">生成时间：{timestamp.strftime("%Y年%m月")}</span>'
        + "</div>"
        + cover_cards
        + f'<div class="map-frame">{map_html}</div>'
        + '<div class="map-legend">'
        '<span><i class="legend-symbol port"></i>港口</span>'
        '<span><i class="legend-symbol choke"></i>咽喉点</span>'
        '<span><i class="legend-symbol asset"></i>油气资产</span>'
        '<span><i class="legend-symbol vessel"></i>船舶（网格聚合点）</span>'
        "<span>底图 Tiles © Esri</span>"
        "</div>" + cover_table
    )

    choke_names = {str(row.get("portid")): display_name(row) for row in choke_catalog}
    n_series = [
        (
            str(choke_names.get(point_id, point_id)),
            [
                (row.get("date"), row.get("n_total"))
                for row in choke_history
                if str(row.get("portid")) == point_id
            ],
        )
        for point_id in sorted({str(row.get("portid")) for row in choke_history})
    ]
    capacity_series = [
        (
            str(choke_names.get(point_id, point_id)),
            [
                (row.get("date"), row.get("capacity"))
                for row in choke_history
                if str(row.get("portid")) == point_id
            ],
        )
        for point_id in sorted({str(row.get("portid")) for row in choke_history})
    ]
    choke_content = (
        '<p class="note">按通道分别呈现每日源站记录。不同通道的船次不相加；承载能力为 PortWatch 估算口径。</p>'
        + '<div class="chart-grid">'
        + _time_series_chart("咽喉点每日通过船次", n_series, "艘次/日")
        + _time_series_chart(
            "咽喉点估算承载能力", capacity_series, "载重吨/日（源站口径）"
        )
        + "</div><h3>最近7日与前7日</h3>"
        + _change_table(choke_history, choke_catalog, choke_day)
    )

    history_ids = sorted({str(row.get("portid")) for row in port_history})
    port_name = {str(row.get("portid")): display_name(row) for row in port_catalog}
    node_daily = _history_by_node(port_history)
    latest_daily = latest_by_node(port_history)
    top_ids = sorted(
        history_ids,
        key=lambda pid: _number((latest_daily.get(pid) or {}).get("portcalls")) or 0,
        reverse=True,
    )[:6]
    port_series = [
        (
            str(port_name.get(pid, pid)),
            [(row.get("date"), row.get("portcalls")) for row in node_daily[pid]],
        )
        for pid in top_ids
    ]
    calls, calls_coverage = _aggregate(port_history, "portcalls")
    imports, import_coverage = _aggregate(port_history, "import", scale=10000)
    exports, export_coverage = _aggregate(port_history, "export", scale=10000)
    port_content = (
        '<p class="note">缺报日留空。进出口图按当日有源记录的点位合计，并在表中列出覆盖点位数；'
        "油气货量为 AIS 推算，不是海关实测。</p>"
        + '<div class="chart-grid">'
        + _time_series_chart("重点港口每日有效进港艘次", port_series, "艘次/日")
        + _time_series_chart(
            "港口估算进出口货量", [("进口", imports), ("出口", exports)], "万吨/日"
        )
        + "</div><h3>港口记录覆盖与最新值</h3>"
    )
    coverage_days = sorted(
        set(calls_coverage) | set(import_coverage) | set(export_coverage)
    )
    coverage_rows = []
    for day in coverage_days[-14:]:
        coverage_rows.append(
            [
                day,
                f"{calls_coverage.get(day, 0)}/{len(stat_ports)}",
                f"{_fmt(dict(calls).get(day), 0)}",
                f"{import_coverage.get(day, 0)}/{len(stat_ports)}",
                f"{export_coverage.get(day, 0)}/{len(stat_ports)}",
            ]
        )
    port_content += _table(
        [
            "日期 UTC",
            "有进港记录点位",
            "进港艘次合计",
            "有进口记录点位",
            "有出口记录点位",
        ],
        coverage_rows,
    )
    top_ports = sorted(
        latest_ports,
        key=lambda row: (
            _number(row.get("portcalls"))
            if _number(row.get("portcalls")) is not None
            else -1
        ),
        reverse=True,
    )[:12]
    port_content += "<h3>港口最新日记录（最多12个）</h3>" + _table(
        [
            "港口",
            "国家",
            "观测日 UTC",
            "有效进港艘次",
            "估算进口（万吨）",
            "估算出口（万吨）",
        ],
        [
            [
                port_name.get(str(row.get("portid")), display_name(row)),
                row.get("country"),
                row.get("date"),
                _fmt(row.get("portcalls")),
                _fmt((_number(row.get("import")) or 0) / 10000, 2)
                if _number(row.get("import")) is not None
                else "—",
                _fmt((_number(row.get("export")) or 0) / 10000, 2)
                if _number(row.get("export")) is not None
                else "—",
            ]
            for row in top_ports
        ],
    )

    assets_table_rows = []
    for row in asset_table[:20]:
        assets_table_rows.append(
            [
                display_name(row),
                row.get("国家"),
                row.get("生产状态"),
                row.get("产量显示") or row.get("本层级日产量"),
                row.get("其他日量指标")
                if row.get("其他日量指标") not in (None, "—")
                else row.get("指标口径"),
                row.get("数据日期"),
                row.get("产量口径说明")
                or row.get("合计口径说明")
                or row.get("地图坐标精度"),
            ]
        )
    oil_content = (
        '<p class="note">只列公开披露且可定位的战略节点；实际产量、产能、目标与历史值按资产逐项区分，'
        "不跨口径相加。坐标精度以来源标注为准；未核实独立位置的资产仅列目录。</p>"
        + '<div class="map-frame">'
        + _overview_map([], [], report_assets, regions)
        + "</div>"
        + "<h3>战略油气资产（最多20项）</h3>"
        + _table(
            [
                "资产",
                "国家",
                "状态",
                "产量／注明范围的合计参考",
                "其他指标",
                "披露日期",
                "合计／权益口径说明",
            ],
            assets_table_rows,
        )
        + "<h3>产量来源与检索结论（对应以上资产）</h3>"
        + _table(
            ["资产", "产量检索复核", "资产指标来源", "合计参考来源"],
            [
                [
                    display_name(row),
                    row.get("产量检索复核"),
                    row.get("来源链接"),
                    row.get("合计参考证据链接"),
                ]
                for row in asset_table[:20]
            ],
        )
    )
    reference_rows = [row for row in asset_table[:20] if row.get("GEM Unit ID")]
    if reference_rows:
        oil_content += (
            "<h3>公开目录背景（2026-03版本；最多20项）</h3>"
            '<p class="note">Global Energy Monitor（CC BY 4.0）公开镜像；运营商和权益仅为目录参考，'
            "投产年不表示当前在产；未披露字段保持为空。</p>"
            + _table(
                [
                    "资产",
                    "运营商（参考）",
                    "发现年",
                    "商业投产年",
                    "GEM ID",
                    "固定版本来源",
                ],
                [
                    [
                        display_name(row),
                        row.get("运营商（2026-03目录参考）"),
                        row.get("发现年（目录参考）"),
                        row.get("商业投产年（目录参考）"),
                        row.get("GEM Unit ID"),
                        row.get("参考资料链接"),
                    ]
                    for row in reference_rows
                ],
            )
        )

    ais_content = (
        '<p class="note">AIS 是事件驱动的公开/订阅观测快照，不是监测水域内全部船舶的普查；'
        "点位可能受接收站覆盖和报文年龄影响。</p>"
        + _metric_cards(
            [
                ("快照船位", str(len(vessels)) if vessels else "—", ais_source_note),
                (
                    "航行中",
                    str(sum(bool(row.get("moving")) for row in vessels))
                    if vessels
                    else "—",
                    "航速至少0.5节",
                ),
                (
                    "油轮/液货船",
                    str(sum(row.get("category") == "tanker" for row in vessels))
                    if vessels
                    else "—",
                    "按AIS基础船型分类",
                ),
                ("数据来源", ais_status, "以当前会话可用状态为准"),
            ]
        )
        + '<div class="map-frame">'
        + _overview_map([], [], [], regions, vessels)
        + "</div>"
        + _distribution(vessels)
    )

    source_content = _table(
        ["数据", "来源", "更新与解释边界"],
        [
            [
                "港口日活动",
                "IMF PortWatch",
                "每日源站汇总；受AIS识别、挂靠规则和发布时间影响；缺报不补零。",
            ],
            ["咽喉点日活动", "IMF PortWatch", "总船次与承载能力按每个通道单独解释。"],
            [
                "AIS船位",
                "Open Waters / 可选 AISStream",
                "公开快照与WebSocket事件按MMSI去重；观测数量不等于总船数。",
            ],
            [
                "油气资产",
                "公开披露及项目核验目录",
                "状态、产量、产能和目标保留各自日期与指标口径。",
            ],
            [
                "油气目录背景",
                "Global Energy Monitor / CC BY 4.0 公开镜像",
                "2026-03版本；运营商、发现和投产年份仅为参考，不据此填补日产量或当前停复产状态。",
            ],
        ],
    )
    source_content += "<h3>异常与缺报</h3>" + _table(
        ["检查项", "当前状态"],
        [
            [f"报告数据获取：{index + 1}", error]
            for index, error in enumerate(errors or [])
        ],
        empty="本次报告数据请求未返回错误；空值仍按源站缺报处理。",
    )
    source_content += '<p class="note">港口进口/出口货量是 PortWatch 基于 AIS 推算的估算值；AIS 船位点不能替代逐船航迹；油气目录中的静态披露不能作为实时生产监测。</p>'

    body = (
        f'<section class="report-cover report-overview">{overview}</section>'
        + _section("战略通道运输", choke_content, page=True)
        + _section("港口运输活动", port_content, page=True)
        + _section("油气供给与资产", oil_content, page=True)
        + _section("AIS 船位观测", ais_content, page=True)
        + _section("数据来源与口径", source_content, page=True)
    )
    return f'<div class="print-report">{body}</div>'


PRINT_CSS = """
<style>
.print-report { display: none; color: #17212b; background: #fff; font: 10pt/1.38 Arial, "Noto Sans CJK SC", sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.print-report * { box-sizing: border-box; }
@media print { .print-report { display: block !important; } }
.report-masthead { display:flex; justify-content:space-between; align-items:baseline; gap:4mm; border-bottom:1px solid #9aa7b4; padding-bottom:2mm; margin-bottom:2mm; font-size:9pt; }
.report-sponsor { text-align:left; font-size:9pt; font-weight:400!important; }
.report-generated { text-align:right; white-space:nowrap; }
.print-report h1.report-title { text-align:left; font-size:15pt; margin:0 0 2mm; line-height:1.15; }
.map-legend { display:flex; justify-content:center; flex-wrap:wrap; gap:2mm 5mm; font-size:8pt; margin:1mm 0 2mm; }
.map-legend .legend-symbol { display:inline-flex; width:3mm; height:3mm; margin-right:1mm; vertical-align:middle; align-items:center; justify-content:center; }
.legend-symbol.port { background:#7c3aed; clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%); }
.legend-symbol.choke { border:0.45mm solid #7c3aed; border-radius:50%; background:#fff; }
.legend-symbol.asset { background:#111; clip-path:polygon(50% 0,0 100%,100% 100%); }
.legend-symbol.vessel { width:2mm; height:2mm; border-radius:50%; background:#dc2626; }
.print-report h2 { font-size: 15pt; border-bottom: 1px solid #9aa7b4; padding-bottom: 2mm; margin: 0 0 4mm; }
.print-report h3 { font-size: 10.5pt; margin: 4mm 0 2mm; }
.report-page { break-before: page; page-break-before: always; }
.print-report .monitoring-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:3mm; margin:4mm 0; }
.print-report .monitoring-card { border:1px solid #ccd5de; border-radius:2mm; padding:3mm; min-width:0; }
.print-report .monitoring-card span, .print-report .monitoring-card-detail { display:block; color:#334155; font-size:10pt; overflow-wrap:anywhere; }
.print-report .monitoring-card strong { display:block; font-size:14pt; margin:1.5mm 0; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2mm; margin: 2mm 0 3mm; }
.metric-card { border: 1px solid #ccd5de; border-radius: 2mm; padding: 2mm; min-width: 0; }
.metric-card span, .metric-card small { display: block; color: #516171; font-size: 8pt; }
.metric-card strong { display: block; font-size: 15pt; margin: .5mm 0 0; overflow-wrap: anywhere; }
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:4mm; align-items:start; }
.chart-card { border:1px solid #d6dde5; padding:2mm; break-inside:avoid; page-break-inside:avoid; min-width:0; }
.chart-card h3 { margin:1mm 1mm 0; }
.chart-legend { display:flex; flex-wrap:wrap; gap:1mm 3mm; margin:1mm; font-size:7pt; }
.chart-legend i { display:inline-block; width:2mm; height:2mm; margin-right:1mm; }
.chart-scale { display:block; margin:0 1mm; color:#52606d; font-size:6.5pt; }
.chart-series-row { display:flex; align-items:center; gap:2mm; margin:1mm 0; }
.chart-series-label { width:20%; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:7pt; }
.chart-bars { display:flex; align-items:flex-end; flex:1; height:16mm; min-width:0; border-bottom:1px solid #9aa7b4; background:repeating-linear-gradient(to bottom, transparent 0, transparent calc(25% - 1px), #e8edf2 25%); }
.chart-bar { display:block; flex:1 1 0; min-width:0; margin-right:.35px; }
.chart-bar.missing { height:1px; background:transparent !important; border-top:1px dotted #aab4be; }
.chart-date-labels { display:flex; justify-content:space-between; margin-left:22%; color:#52606d; font-size:6.5pt; }
.unit,.note,.empty { color:#52606d; font-size:8pt; }
.note { margin:2mm 0; }
.map-frame { border:1px solid #d6dde5; padding:1mm; break-inside:avoid; page-break-inside:avoid; }
.overview-map { position:relative; width:100%; background:#d6eef4; border:1px solid #94a3b8; }
.overview-map-plot { position:absolute; inset:0; overflow:hidden; background:#d6eef4; }
.map-tile { position:absolute; z-index:0; max-width:none; }
.choke-leaders { position:absolute; inset:0; width:100%; height:100%; overflow:visible; z-index:2; pointer-events:none; }
.choke-leaders path { fill:none; stroke:#475569; stroke-width:1.8; vector-effect:non-scaling-stroke; }
.map-point { position:absolute; z-index:3; display:block; transform:translate(-50%,-50%); }
.map-point.port { width:1.8mm; height:1.8mm; background:#7c3aed; clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%); }
.map-point.asset { width:1.6mm; height:1.6mm; background:#111; clip-path:polygon(50% 0,0 100%,100% 100%); }
.map-point.choke { width:2.1mm; height:2.1mm; border:.4mm solid #7c3aed; border-radius:50%; background:#fff; }
.choke-label { position:absolute; z-index:4; transform:translateY(-100%); color:#1f2937; font-size:7.5pt; line-height:1.15; white-space:nowrap; font-weight:600; text-shadow:0 0 2px #fff,0 0 2px #fff,0 0 3px #fff; }
.choke-label.left { transform:translate(0,-100%); }
.choke-label.right { transform:translate(-100%,-100%); }
.map-point.vessel { width:1.35mm; height:1.35mm; border-radius:50%; background:#dc2626; }
.table-wrap { overflow:visible; }
.print-report table { width:100%; border-collapse:collapse; font-size:8pt; margin:2mm 0 4mm; }
.print-report th,.print-report td { border:1px solid #cbd5df; padding:1.3mm 1.6mm; text-align:left; vertical-align:top; overflow-wrap:anywhere; }
.print-report th { background:#eef2f6; font-weight:700; }
.print-report thead { display:table-header-group; }
.print-report tr { break-inside:avoid; page-break-inside:avoid; }
</style>
"""
