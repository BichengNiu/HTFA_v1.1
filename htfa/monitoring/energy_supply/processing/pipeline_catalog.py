"""Read-only pipeline evidence and escaped popup content."""
import math
import re
from datetime import date
from urllib.parse import urlsplit

import htfa.monitoring.energy_supply.data.storage as data_store
from htfa.monitoring.energy_supply.processing.pipeline_capacity import (
    million_bpd,
    review_digest,
)

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
    document = data_store.read_json(PROJECT_DOCUMENT)
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
