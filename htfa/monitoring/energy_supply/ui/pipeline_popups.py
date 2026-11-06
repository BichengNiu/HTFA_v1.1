"""Escaped pipeline popup presentation for validated pipeline records."""

from html import escape
from urllib.parse import urlsplit

from htfa.monitoring.energy_supply.processing.pipeline_capacity import (
    display as capacity_display,
)
from htfa.monitoring.energy_supply.processing.pipeline_capacity import million_bpd
from htfa.monitoring.energy_supply.processing.pipeline_catalog import (
    ACCURACY,
    COUNTRY_NAMES,
    STATUSES,
)


def unmapped_popup(p):
    fields = [
        ("国家", "、".join(COUNTRY_NAMES.get(c, c) for c in p["countries"])),
        ("资料记载状态", STATUSES[p["status"]]),
        *([("状态依据", p["status_note"])] if p.get("status_note") else []),
        ("预计投产", p.get("expected_start_year") or "未公布"),
        ("原油运力", "未公布独立数值（百万桶/日）"),
        ("项目目标", p.get("purpose") or "—"),
        ("线路资料", p.get("geometry_note") or "尚无可核验的公开线路坐标"),
        ("资料日期", p["source_date"]),
    ]
    return (
        '<div class="popup-card"><div class="field-name">'
        + escape(p["name"])
        + "</div>"
        + "".join(
            f'<div class="row"><span>{escape(k)}</span><strong>{escape(str(v))}</strong></div>'
            for k, v in fields
        )
        + f'<a href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">来源</a></div>'
    )


def gas_popup(p):
    title = escape(p["name"])
    rows = [
        ("介质", "天然气（不属于原油运力）"),
        (
            "分段",
            {
                "Offshore Segment": "海上段（Offshore Segment）",
                "Onshore Segment": "陆上段（Onshore Segment）",
            }.get(p.get("segment"), p.get("segment")),
        ),
        ("GEM编号", p["project_id"]),
        ("资料记载状态", STATUSES[p["status"]] + "（非实时）"),
        ("资料更新日", p.get("updated_at")),
    ]
    return (
        f'<div class="field-name">{title}</div>'
        + "".join(
            f'<div class="row"><span>{label}</span><strong>{escape(str(value or "未披露"))}</strong></div>'
            for label, value in rows
        )
        + f'<div style="font-size:14px;line-height:1.5;margin-top:10px;color:#172033">路线核查：{escape(p["geometry_review_note"])}</div>'
        + f'<a class="source" href="{escape(p["connection_source_url"], quote=True)}" target="_blank" rel="noopener">ADNOC Gas · 连接关系</a>'
        + f'<a class="source" href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">Global Energy Monitor · 示意路线 · CC BY 4.0</a>'
    )


def popup(p):
    if p.get("fuel") == "Gas":
        return gas_popup(p)

    def text(value):
        return escape(str(value if value not in (None, "", "--") else "未披露"))

    value = (
        p.get("capacity_million_bpd")
        if "capacity_million_bpd" in p
        else million_bpd(p.get("capacity"), p.get("capacity_unit"))
    )
    capacity_text = capacity_display(
        value, approximate=p.get("capacity_approximate", False)
    )
    if p.get("capacity_range_million_bpd"):
        capacity_text = "—".join(p["capacity_range_million_bpd"]) + " 百万桶/日"
    if p.get("capacity_review_status") == "conflict_withheld":
        capacity_text = "待核实"
    rows = [
        ("GEM编号", p["project_id"]),
        ("分段", p.get("segment")),
        ("国家/地区", "、".join(COUNTRY_NAMES.get(x, x) for x in p["countries"])),
        ("起点", p.get("start")),
        ("终点", p.get("end")),
        ("资料记载状态", STATUSES[p["status"]] + "（非实时）"),
        (p.get("capacity_display_label") or "公开运力", capacity_text),
        *[
            (
                row["label"],
                capacity_display(row["value_million_bpd"]) + "；" + row["note"],
            )
            for row in p.get("capacity_extra", [])
        ],
        ("运力口径", p.get("capacity_basis") or "源表标称值；非实际日输送量"),
        ("运力资料期", p.get("capacity_reference_date") or p.get("updated_at")),
        ("资料更新日", p.get("updated_at")),
        (
            "路线",
            (
                ACCURACY.get(p.get("route_accuracy"), p.get("route_accuracy"))
                or "源精度未披露"
            )
            + "；地图已简化约0.003°",
        ),
    ]
    if p.get("capacity") and p.get("capacity_unit") == "mtpa":
        rows.insert(
            7,
            ("原始质量单位", f"{p['capacity']} 百万吨/年；缺少密度，未换算为百万桶/日"),
        )
    reference = p.get("capacity_reference_url")
    reference_link = ""
    if (
        reference
        and reference != p["source_url"]
        and urlsplit(reference).scheme == "https"
    ):
        reference_link = f'<a class="source" href="{escape(reference, quote=True)}" target="_blank" rel="noopener">运力核查原始来源</a>'
    return (
        f'<div class="field-name">{text(p["name"])}</div>'
        + "".join(
            f'<div class="row"><span>{label}</span><strong>{text(value)}</strong></div>'
            for label, value in rows
        )
        + f'<a class="source" href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">Global Energy Monitor · 管线资料</a>'
        + reference_link
        + '<a class="source" href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0 · 路线经筛选及简化</a>'
    )
