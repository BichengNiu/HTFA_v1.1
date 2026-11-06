"""Read-only pipeline evidence and escaped popup content."""
from datetime import date
from html import escape
import math
import re
from urllib.parse import urlsplit

from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply.pipeline_capacity import display as capacity_display, million_bpd, review_digest

DOCUMENT = "data/oil_pipelines.geojson"
PROJECT_DOCUMENT = "data/pipeline_projects.json"
STATUSES = {
    "operating": "运行中", "construction": "建设中", "proposed": "规划中",
    "idle": "闲置", "mothballed": "封存", "retired": "退役",
    "cancelled": "取消", "shelved": "搁置",
    "unknown": "当前状态待核实",
}
COUNTRY_NAMES = {
    "Saudi Arabia": "沙特阿拉伯", "Iraq": "伊拉克", "Iran": "伊朗",
    "United Arab Emirates": "阿联酋", "Egypt": "埃及", "Oman": "阿曼",
    "Kuwait": "科威特", "Qatar": "卡塔尔", "Yemen": "也门", "Syria": "叙利亚",
    "Turkey": "土耳其", "Türkiye": "土耳其", "Israel": "以色列", "Jordan": "约旦",
    "Lebanon": "黎巴嫩", "Bahrain": "巴林", "Azerbaijan": "阿塞拜疆", "Georgia": "格鲁吉亚",
    "Libya": "利比亚", "Palestine": "巴勒斯坦",
}
ACCURACY = {
    "very high (within meters)": "源路线精度：米级",
    "high": "源路线精度：高", "medium": "源路线精度：中",
    "low": "源路线精度：低", "very low (straight line/schematic)": "源路线为直线或示意",
}


def load_unmapped_projects():
    """Published project records whose source does not expose a route geometry."""
    try:
        document = data_store.read_json(PROJECT_DOCUMENT)
    except FileNotFoundError:
        return []  # Older snapshots remain usable during code/data deployment.
    projects = document["projects"]
    ids = set()
    for row in projects:
        if (row["project_id"] in ids or row.get("geometry") is not None
                or row.get("status") not in STATUSES or row.get("fuel") != "Oil"
                or not row.get("source_url", "").startswith("https://")):
            raise ValueError("未映射管线项目证据无效")
        if not re.search(r"[\u3400-\u9fff]", row["name_cn"]) or row["name"] != f'{row["name_cn"]}（{row["name_en"]}）':
            raise ValueError("未映射管线项目双语名称无效")
        ids.add(row["project_id"])
    return projects


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
    return ('<div class="popup-card"><div class="field-name">'+escape(p['name'])+'</div>'
            + ''.join(f'<div class="row"><span>{escape(k)}</span><strong>{escape(str(v))}</strong></div>' for k,v in fields)
            + f'<a href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">来源</a></div>')


def validate(document, *, expected_fuel="Oil"):
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        raise ValueError("输油管线快照为空或格式错误")
    metadata = document["metadata"]
    if metadata.get("license") != "CC BY 4.0" or len(metadata.get("source_sha256", "")) != 64:
        raise ValueError("输油管线快照缺少许可或来源校验信息")
    seen = set()
    for feature in document["features"]:
        p, geometry = feature["properties"], feature["geometry"]
        if p["project_id"] in seen or p.get("fuel") != expected_fuel or p.get("status") not in STATUSES:
            raise ValueError("输油管线分段重复、类型或状态无效")
        seen.add(p["project_id"])
        if metadata.get("bilingual_names_version") == 1:
            if not re.search(r"[\u3400-\u9fff]", p.get("name_cn", "")) or p["name"] != f"{p['name_cn']}（{p['name_en']}）":
                raise ValueError("管线中文及英文名称不完整")
        if p.get("updated_at"):
            date.fromisoformat(p["updated_at"])
        if metadata.get("capacity_schema_version") == 2:
            if "capacity_million_bpd" not in p or not p.get("capacity_review_status"):
                raise ValueError("输油管线缺少运力核查结果")
            values = [p["capacity_million_bpd"], *p.get("capacity_range_million_bpd", []),
                      *(row["value_million_bpd"] for row in p.get("capacity_extra", []))]
            for value in values:
                if value is not None:
                    # Reuse the finite/nonnegative guard, without an extra conversion.
                    million_bpd(value, "bpd")
            if p["capacity_review_status"] in {"conflict_withheld", "equal_split_withdrawn", "mass_unit_not_converted", "source_missing"} and p["capacity_million_bpd"] is not None:
                raise ValueError("未核实的运力不能显示为确定值")
            if p["capacity_million_bpd"] is not None and p["capacity_review_status"] != "primary_capacity_confirmed":
                if p["capacity_million_bpd"] != million_bpd(p.get("capacity"), p.get("capacity_unit")):
                    raise ValueError("运力换算与原始单位不一致")
        url = urlsplit(p["source_url"])
        if url.scheme != "https" or not (url.hostname == "www.gem.wiki" or p["source_url"] == metadata["source_url"]):
            raise ValueError("输油管线来源链接无效")
        if geometry["type"] not in ("LineString", "MultiLineString"):
            raise ValueError("输油管线必须为线几何")
        lines = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
        if not lines:
            raise ValueError("输油管线路线为空")
        for line in lines:
            if len(line) < 2:
                raise ValueError("输油管线路线点不足")
            for lon, lat in line:
                if not all(math.isfinite(x) for x in (lon, lat)) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("输油管线坐标超出范围")
    return document


def load():
    document = validate(data_store.read_json(DOCUMENT))
    if document["metadata"].get("capacity_schema_version") == 2:
        review = data_store.read_json("data/pipeline_capacity_review.json")
        if review_digest(review) != document["metadata"]["capacity_review_sha256"]:
            raise ValueError("运力核查记录与管线快照版本不一致")
        rows = {r["project_id"]: r for r in review["records"]}
        if set(rows) != {f["properties"]["project_id"] for f in document["features"]}:
            raise ValueError("运力核查没有覆盖全部管线分段")
        for feature in document["features"]:
            p = feature["properties"]
            if any(p.get(key) != value for key, value in rows[p["project_id"]].items() if key.startswith("capacity_")):
                raise ValueError("地图运力与核查记录不一致")
    return document


def load_gas_connections():
    document = data_store.read_json("data/uae_gas_connections.geojson")
    ids = {f["properties"]["project_id"] for f in document["features"]}
    if ids != {"P5683", "P5711", "P5684"}:
        raise ValueError("阿联酋输气联络证据不完整")
    validate(document, expected_fuel="Gas")
    for feature in document["features"]:
        if feature["properties"].get("connection_source_url") != "https://www.adnocgas.ae/en/our-operations/gas-processing":
            raise ValueError("输气联络缺少运营商证据")
    return document


def gas_popup(p):
    title = escape(p["name"])
    rows = [("介质", "天然气（不属于原油运力）"),
            ("分段", {"Offshore Segment": "海上段（Offshore Segment）", "Onshore Segment": "陆上段（Onshore Segment）"}.get(p.get("segment"), p.get("segment"))), ("GEM编号", p["project_id"]),
            ("资料记载状态", STATUSES[p["status"]] + "（非实时）"),
            ("资料更新日", p.get("updated_at"))]
    return (f'<div class="field-name">{title}</div>'
            + "".join(f'<div class="row"><span>{label}</span><strong>{escape(str(value or "未披露"))}</strong></div>' for label, value in rows)
            + f'<div style="font-size:14px;line-height:1.5;margin-top:10px;color:#172033">路线核查：{escape(p["geometry_review_note"])}</div>'
            + f'<a class="source" href="{escape(p["connection_source_url"], quote=True)}" target="_blank" rel="noopener">ADNOC Gas · 连接关系</a>'
            + f'<a class="source" href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">Global Energy Monitor · 示意路线 · CC BY 4.0</a>')


def popup(p):
    if p.get("fuel") == "Gas":
        return gas_popup(p)

    def text(value):
        return escape(str(value if value not in (None, "", "--") else "未披露"))
    value = p.get("capacity_million_bpd") if "capacity_million_bpd" in p else million_bpd(p.get("capacity"), p.get("capacity_unit"))
    capacity_text = capacity_display(value, approximate=p.get("capacity_approximate", False))
    if p.get("capacity_range_million_bpd"):
        capacity_text = "—".join(p["capacity_range_million_bpd"]) + " 百万桶/日"
    if p.get("capacity_review_status") == "conflict_withheld":
        capacity_text = "待核实"
    rows = [
        ("GEM编号", p["project_id"]),
        ("分段", p.get("segment")),
        ("国家/地区", "、".join(COUNTRY_NAMES.get(x, x) for x in p["countries"])),
        ("起点", p.get("start")), ("终点", p.get("end")),
        ("资料记载状态", STATUSES[p["status"]] + "（非实时）"),
        (p.get("capacity_display_label") or "公开运力", capacity_text),
        *[(row["label"], capacity_display(row["value_million_bpd"]) + "；" + row["note"])
          for row in p.get("capacity_extra", [])],
        ("运力口径", p.get("capacity_basis") or "源表标称值；非实际日输送量"),
        ("运力资料期", p.get("capacity_reference_date") or p.get("updated_at")),
        ("资料更新日", p.get("updated_at")),
        ("路线", (ACCURACY.get(p.get("route_accuracy"), p.get("route_accuracy")) or "源精度未披露") + "；地图已简化约0.003°"),
    ]
    if p.get("capacity") and p.get("capacity_unit") == "mtpa":
        rows.insert(7, ("原始质量单位", f"{p['capacity']} 百万吨/年；缺少密度，未换算为百万桶/日"))
    reference = p.get("capacity_reference_url")
    reference_link = ""
    if reference and reference != p["source_url"] and urlsplit(reference).scheme == "https":
        reference_link = f'<a class="source" href="{escape(reference, quote=True)}" target="_blank" rel="noopener">运力核查原始来源</a>'
    return (
        f'<div class="field-name">{text(p["name"])}</div>'
        + "".join(f'<div class="row"><span>{label}</span><strong>{text(value)}</strong></div>' for label, value in rows)
        + f'<a class="source" href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">Global Energy Monitor · 管线资料</a>'
        + reference_link
        + '<a class="source" href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0 · 路线经筛选及简化</a>'
    )
