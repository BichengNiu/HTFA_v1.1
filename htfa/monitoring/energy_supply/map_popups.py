"""Pure HTML cards and asset labels used by the map, tables, and report."""

from __future__ import annotations

from htfa.monitoring.energy_supply.entity_names import display_name

import html

from htfa.monitoring.energy_supply import field_catalog as CATALOG
from htfa.monitoring.energy_supply import portwatch as PORTWATCH
from htfa.monitoring.energy_supply.asset_values import display_value
from htfa.monitoring.energy_supply.portwatch_records import SHIP_TYPE_LABELS

METRIC_LABELS = {
    "estimated_daily_average": "估算期间日均（公布总量×份额）",
    "actual_output": "来源直报实际产量",
    "estimated_output": "来源披露估计产量",
    "production_acceptance_test": "开发生产验收测试（非持续日产量）",
    "sales_volume": "期间销售量（非产量）",
    "actual_output_boe": "来源实绩（油当量；非原油桶）",
    "derived_daily_average": "历史推算日均产量",
    "capacity": "产能",
    "oil_capacity": "原油产能",
    "target_capacity": "目标产能",
    "maximum_sustainable_capacity": "最大可持续产能",
    "historical_capacity": "历史产能",
    "historical_design_capacity": "历史设计产能",
    "historical_peak": "历史峰值",
    "historical_condensate_output": "历史凝析油产量",
    "incremental_capacity": "新增产能",
    "planned_incremental_capacity": "规划新增产能",
    "undisclosed": "未披露",
}

OUTPUT_METRIC_TYPES = CATALOG.OUTPUT_METRIC_TYPES
ASSET_INDEX = {(a["country"], a["name"]): a for a in CATALOG.ASSETS}


def _esc(value: object) -> str:
    return html.escape(str(value))


def extra_measurements(asset: dict) -> str:
    return (
        "；".join(
            f"{CATALOG.COMMODITY_LABELS[m['commodity']]} {m['value']} {m['unit']}"
            f"（{METRIC_LABELS[m['metric_type']]}，{m['data_date']}；{m['basis']}）"
            for m in asset.get("additional_measurements", [])
        )
        or "未披露"
    )


def display_date(asset: dict[str, object]) -> str:
    return str(asset.get("data_date") or "未提供")


def daily_output_value(asset: dict[str, object]) -> str:
    if asset.get("value") is None or asset.get("metric_type") not in OUTPUT_METRIC_TYPES:
        return "未披露"
    return display_value(asset)


def other_daily_metric(asset: dict[str, object]) -> str:
    if asset.get("value") is None or asset.get("metric_type") in OUTPUT_METRIC_TYPES:
        return "—"
    metric_label = METRIC_LABELS[str(asset["metric_type"])]
    return f"{metric_label}：{display_value(asset)}"


def production_display_value(asset: dict) -> str:
    output = daily_output_value(asset)
    if output != "未披露":
        return output
    references = asset.get("aggregate_references", [])
    if references:
        row = references[0]
        return f'合计参考：{display_value(row)}（{row["scope"]}）'
    return output


def production_display_date(asset: dict) -> str:
    references = asset.get("aggregate_references", [])
    if daily_output_value(asset) == "未披露" and references:
        return str(references[0]["data_date"])
    return display_date(asset)


def aggregate_production_note(asset: dict) -> str:
    return "；".join(
        f'{row["scope"]}（{row["data_date"]}）：{row.get("note") or row.get("basis", "")} '
        f'权益口径：{row["ownership_basis"]}；合计不分配为本田产量，不重复汇总。'
        for row in asset.get("aggregate_references", [])
    )


def hierarchy_chain(asset: dict[str, object]) -> list[dict[str, object]]:
    """返回当前资产到最高已登记上级的链条；防止异常循环。"""

    chain = [asset]
    seen = {(asset["country"], asset["name"])}
    current = asset
    while current.get("parent_asset"):
        parent_key = (current["country"], current["parent_asset"])
        if parent_key in seen:
            break
        parent = ASSET_INDEX.get(parent_key)
        if parent is None:
            break
        chain.append(parent)
        seen.add(parent_key)
        current = parent
    return chain


def related_asset_name(asset, name):
    return display_name(ASSET_INDEX.get((asset["country"], name), {"name": name}))


def hierarchy_path(asset: dict[str, object]) -> str:
    chain = list(reversed(hierarchy_chain(asset)))
    return " → ".join(f"{node['asset_level_label']}：{display_name(node)}" for node in chain)


def _hierarchy_panel(asset: dict[str, object]) -> str:
    cards: list[str] = []
    for node in hierarchy_chain(asset):
        output = daily_output_value(node)
        metric_type = str(node["metric_type"])
        output_detail = (
            f"{METRIC_LABELS[metric_type]} · {display_date(node)}"
            if output != "未披露"
            else "本层级实际／历史日均未披露"
        )
        other = other_daily_metric(node)
        other_html = (
            f'<div class="other-metric">{_esc(other)} · {_esc(display_date(node))}</div>'
            if other != "—"
            else ""
        )
        cards.append(
            '<div class="level-metric">'
            f'<div class="level-head"><span>{_esc(node["asset_level_label"])}</span>'
            f"<b>{_esc(display_name(node))}</b></div>"
            f'<div class="output-line"><span>日产量</span><strong>{_esc(output)}</strong></div>'
            f'<div class="metric-detail">{_esc(output_detail)}</div>'
            f"{other_html}"
            "</div>"
        )
    return "".join(cards)


def _public_metadata_panel(asset: dict) -> str:
    reference = asset.get("public_metadata")
    if not reference:
        return ""
    rows = "".join(
        f'<div class="row"><span>{label}</span><strong>{_esc(reference[key])}</strong></div>'
        for key, label in (
            ("operator", "运营商（目录参考）"),
            ("owners", "权益持有人（目录参考）"),
            ("discoveryYear", "发现年（目录参考）"),
            ("productionStartYear", "商业投产年（目录参考）"),
        )
        if reference.get(key) is not None
    )
    return (
        f'<div class="hierarchy-title">公开目录背景（{_esc(reference["release"])}）</div>'
        + rows
        + '<div class="basis">二手目录参考；投产年不证明当前在产，运营商与权益可能后续变更。'
        '参考点精度未保留，不代表核验油田中心或井位。</div>'
        + f'<a class="source" href="{_esc(reference["source_url"])}" target="_blank" rel="noopener">'
        f'Global Energy Monitor · CC BY 4.0 · {_esc(reference["unitId"])}</a>'
    )


def _aggregate_production_panel(asset: dict) -> str:
    references = asset.get("aggregate_references", [])
    if daily_output_value(asset) != "未披露" or not references:
        return ""
    lines = []
    for row in references:
        lines.append(
            f'<div class="basis"><b>{_esc(row["scope"])}</b>：{_esc(display_value(row))} '
            f'（{_esc(METRIC_LABELS[row["metric_type"]])}；{_esc(row["data_date"])}）。'
            f'范围说明：{_esc(row.get("note") or row.get("basis", ""))} '
            f'权益：{_esc(row["ownership_basis"])}。'
            f'<a href="{_esc(row["source_url"])}" target="_blank" rel="noopener">合计来源</a></div>'
        )
    return (
        '<div class="hierarchy-title">产量合计参考（本田逐田值未披露）</div>'
        + "".join(lines)
        + '<div class="basis">合计仅供所属范围参考；未分配为本田产量，不重复汇总。</div>'
    )


def asset_popup(asset: dict[str, object]) -> str:
    """Exactly the selected table fields; all values share the table binding."""
    cards = []
    for row in asset.get("production_rows", []):
        fields = []
        for field, value in row.items():
            if field == "数据来源" and str(value or "").startswith(("https://", "http://")):
                content = (f'<a href="{_esc(value)}" target="_blank" rel="noopener">'
                           f'{_esc(value)}</a>')
            else:
                content = _esc("—" if value is None else value)
            fields.append(f'<div class="row"><span>{_esc(field)}</span><strong>{content}</strong></div>')
        cards.append('<div class="popup-card asset-table-popup">' + ''.join(fields) + '</div>')
    return ''.join(cards)


def port_popup(port: dict, day: str) -> str:
    def count(value):
        return "—" if value is None else f"{value:,.0f}"

    weekly_calls = port.get("week_calls")
    colors = {"container": "#2563eb", "dry_bulk": "#b45309",
              "general_cargo": "#64748b", "roro": "#7c3aed", "tanker": "#0f766e"}
    structure = []
    for kind, label in SHIP_TYPE_LABELS.items():
        share = port.get(f"week_share_{kind}")
        calls = port.get(f"week_calls_{kind}")
        width = max(0, min(100, share or 0))
        share_text = f"{share:.1f}%" if share is not None else "—"
        structure.append(
            '<div class="mix-row">'
            f'<span>{label}</span><div class="mix-track"><i style="width:{width:.1f}%;background:{colors[kind]}"></i></div>'
            f'<b>{count(calls)}艘次（{share_text}）</b></div>'
        )
    daily_calls = port.get("portcalls") if port.get("has_data") else None
    return (
        '<div class="popup-card port-popup">'
        f'<div class="field-name">⚓ {_esc(display_name(port))}</div>'
        f'<div class="row"><span>当日进港艘次</span><strong>{count(daily_calls)} 艘次</strong></div>'
        f'<div class="row"><span>本周累计艘次</span><strong>{count(weekly_calls)} 艘次</strong></div>'
        '<div class="hierarchy-title">本周各船型累计艘次</div>'
        + "".join(structure)
        + "</div>"
    )


def chokepoint_popup(point: dict, day: str) -> str:
    def value(key: str, divisor: float = 1, decimals: int = 0) -> str:
        raw = point.get(key)
        return "—" if raw is None else f"{raw / divisor:,.{decimals}f}"

    categories = SHIP_TYPE_LABELS.items()
    rows = "".join(
        '<div class="row"><span>' + label + "</span>"
        f"<strong>{value(f'n_{kind}')} 艘 · {value(f'capacity_{kind}', 10000, 1)} 万吨</strong></div>"
        for kind, label in categories
    )
    return (
        '<div class="popup-card">'
        f'<div class="field-name">◆ {_esc(display_name(point))}</div>'
        f'<div class="country">{_esc(point.get("fullname") or point["portname"])} · {_esc(day)} UTC</div>'
        '<div class="row"><span>当日通过船舶</span>'
        f"<strong>{value('n_total')} 艘</strong></div>"
        '<div class="row"><span>估算承载货量</span>'
        f"<strong>{value('capacity', 10000, 1)} 万吨</strong></div>"
        '<div class="hierarchy-title">船型分解 · 艘数 / 估算货量</div>'
        f"{rows}"
        '<div class="basis">PortWatch按船舶穿越咽喉点边界计数；跨越多日的同一次通行只计一次，'
        "48小时内同船再次出现不重复计数。货量由AIS、吃水与载重能力估算。</div>"
        f'<a class="source" href="{_esc(PORTWATCH.SOURCE)}" target="_blank" rel="noopener">IMF PortWatch 数据与方法</a>'
        "</div>"
    )
