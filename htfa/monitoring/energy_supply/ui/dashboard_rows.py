"""Pure record-to-table transformations; missing values stay missing."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import htfa.monitoring.energy_supply.processing.ais as AIS
import htfa.monitoring.energy_supply.processing.portwatch as PORTWATCH
from htfa.monitoring.energy_supply.contracts.records import SHIP_TYPE_LABELS
from htfa.monitoring.energy_supply.processing.entity_names import display_name
from htfa.monitoring.energy_supply.processing.port_inventory import country_label
from htfa.monitoring.energy_supply.processing.port_types import (
    port_business_label,
    port_type_label,
)
from htfa.monitoring.energy_supply.processing.vessel_display import (
    destination_label,
    reception_time,
    source_label,
)
from htfa.monitoring.energy_supply.ui.map_popups import (
    METRIC_LABELS,
    aggregate_production_note,
    daily_output_value,
    display_date,
    extra_measurements,
    hierarchy_path,
    other_daily_metric,
    production_display_date,
    production_display_value,
    related_asset_name,
)


def _rounded(value, digits: int = 1, divisor: int = 1):
    if value is None:
        return None
    return round(value / divisor if divisor != 1 else value, digits)


def port_rows(ports: list[dict], selected_day: date | None) -> list[dict]:
    ordered = sorted(
        ports,
        key=lambda port: (
            not bool(port.get("has_data")),
            -(port.get("portcalls") or 0),
            display_name(port),
        ),
    )
    return [
        {
            "港口名": display_name(port),
            "港口类型": port_type_label(port),
            "业务特点": port_business_label(port),
            "国家": country_label(port.get("country")),
            "水域": port.get("region"),
            "日期": selected_day.isoformat() if selected_day else None,
            "当日进港艘次": port.get("portcalls") if port.get("has_data") else None,
            "本周累计艘次": port.get("week_calls"),
            **{
                f"本周{label}累计艘次": port.get(f"week_calls_{kind}")
                for kind, label in SHIP_TYPE_LABELS.items()
            },
            "本月累计艘次": port.get("month_calls"),
            **{
                f"本月{label}累计艘次": port.get(f"month_calls_{kind}")
                for kind, label in SHIP_TYPE_LABELS.items()
            },
            "纬度": port.get("lat"),
            "经度": port.get("lon"),
            "来源": port.get("source_url", PORTWATCH.SOURCE),
        }
        for port in ordered
    ]


def port_metrics(
    ports: list[dict], selected_day: date | None = None
) -> list[tuple[str, object]]:
    covered = [p for p in ports if PORTWATCH.has_independent_statistics(p)]

    def valid(value):
        return value is not None and math.isfinite(value) and value >= 0

    week_fields = ["week_calls", *(f"week_calls_{kind}" for kind in SHIP_TYPE_LABELS)]
    weekly = [p for p in covered if all(valid(p.get(field)) for field in week_fields)]

    def total(key, daily=False):
        cohort = (
            [p for p in covered if p.get("has_data") and valid(p.get(key))]
            if daily
            else weekly
        )
        values = [p[key] for p in cohort]
        return sum(values) if values else None

    def count(value):
        return "—" if value is None else f"{value:,.0f}"

    def chinese_day(day):
        return day.strftime("%Y年%m月%d日")

    day_suffix = f"\n（{chinese_day(selected_day)}）" if selected_day else ""
    week_suffix = (
        (
            f"\n（{chinese_day(selected_day - timedelta(days=selected_day.weekday()))}-"
            f"{chinese_day(selected_day)}）"
        )
        if selected_day
        else ""
    )
    week_total = total("week_calls")
    metrics = [
        ("港口总数", len(ports)),
        ("当日进港艘次" + day_suffix, count(total("portcalls", True))),
        ("本周累计艘次" + week_suffix, count(week_total)),
    ]
    for kind, label in SHIP_TYPE_LABELS.items():
        calls = total(f"week_calls_{kind}")
        share = calls / week_total * 100 if calls is not None and week_total else None
        value = (
            f"{count(calls)}（{share:.1f}%）"
            if share is not None
            else f"{count(calls)}（—）"
        )
        metrics.append((f"本周{label}艘次/占比{week_suffix}", value))
    return metrics


def asset_rows(assets: list[dict]) -> list[dict]:
    asset_index = {(a["country"], a["name"]): a for a in assets}
    return [
        {
            "国家": asset["country"],
            "资产层级": asset["asset_level_label"],
            "共享国家": "、".join(asset["countries"]),
            "权益口径": asset["ownership_basis"],
            "地图角色": asset["map_role_label"],
            "层级路径": hierarchy_path(asset, asset_index),
            "上级资产": related_asset_name(asset, asset["parent_asset"], asset_index)
            if asset["parent_asset"]
            else "—",
            "组成资产": "、".join(
                related_asset_name(asset, name, asset_index)
                for name in asset["constituent_assets"]
            )
            or "—",
            "汇总规则": asset["rollup_policy"],
            "名称": display_name(asset),
            "英文名称": asset["name"],
            "中文名称": asset["name_cn"],
            "别名": "、".join(asset["aliases"]),
            "运营商（2026-03目录参考）": asset.get("public_metadata", {}).get(
                "operator"
            ),
            "权益持有人（2026-03目录参考）": asset.get("public_metadata", {}).get(
                "owners"
            ),
            "发现年（目录参考）": asset.get("public_metadata", {}).get("discoveryYear"),
            "商业投产年（目录参考）": asset.get("public_metadata", {}).get(
                "productionStartYear"
            ),
            "海陆位置（目录原文）": asset.get("public_metadata", {}).get(
                "onshoreOffshore"
            ),
            "GEM Unit ID": asset.get("public_metadata", {}).get("unitId"),
            "参考资料版本": asset.get("public_metadata", {}).get("release"),
            "参考资料复核日": asset.get("public_metadata", {}).get("review_date"),
            "参考资料置信度": asset.get("public_metadata", {}).get("confidence"),
            "参考资料限制": asset.get("public_metadata", {}).get("limitations"),
            "参考资料链接": asset.get("public_metadata", {}).get("source_url"),
            "参考资产页面": asset.get("public_metadata", {}).get("wikiUrl"),
            "数据时效提示": asset["freshness_note"],
            "数值复核": asset["numeric_audit"],
            "数据复核日": asset["data_audit_date"],
            "其他商品指标": extra_measurements(asset),
            "待核验GEM产量线索": json.dumps(
                asset.get("gem_production_candidates", []),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "产量显示": production_display_value(asset),
            "产量显示日期": production_display_date(asset),
            "合计口径说明": aggregate_production_note(asset),
            "合计参考日期": "；".join(
                row["data_date"] for row in asset.get("aggregate_references", [])
            ),
            "合计参考证据链接": "；".join(
                row["source_url"] for row in asset.get("aggregate_references", [])
            ),
            "产量检索复核": asset.get("production_review", {}).get("conclusion"),
            "资产类型": asset["asset_type"],
            "商品": asset["commodity_label"],
            "生产状态": asset["operating_status_label"],
            "状态截至": asset["operating_status_as_of"],
            "本层级日产量": daily_output_value(asset),
            "本层级指标原值": str(asset["value"])
            if asset["value"] is not None
            else None,
            "本层级指标原单位": asset["unit"],
            "其他日量指标": other_daily_metric(asset),
            "指标口径": METRIC_LABELS[asset["metric_type"]],
            "数据日期": display_date(asset),
            "统计范围": asset["aggregation_scope"],
            "状态置信度": asset["operating_status_confidence"],
            "状态依据": asset["operating_status_basis"],
            "状态证据链接": asset["operating_status_evidence_url"],
            "地图坐标精度": asset["map_coordinate_precision"],
            "地图参考纬度": asset["map_lat"],
            "地图参考经度": asset["map_lon"],
            "定位属性": "资产点位"
            if asset.get("map_drawable")
            else "仅列目录；坐标待核",
            "坐标来源": asset["coordinate_source"],
            "坐标来源链接": asset["coordinate_source_url"],
            "战略层级标签": "是" if asset["strategic_default"] else "否",
            "来源": asset["source"],
            "来源链接": asset["source_url"],
            "说明": asset["note"],
        }
        for asset in assets
    ]


def vessel_rows(vessels: list[dict]) -> list[dict]:
    return [
        {
            "水域": vessel.get("region"),
            "船名": vessel.get("name") or "—",
            "船籍": vessel.get("flag_country") or vessel.get("flag") or "—",
            "船型": vessel.get("category_label"),
            "MMSI": vessel.get("mmsi"),
            "IMO": vessel.get("imo"),
            "航行状态": vessel.get("navigation_status"),
            "航速 节": (
                round(vessel["sog"], 1) if vessel.get("sog") is not None else None
            ),
            "航向 °": (
                round(vessel["course"], 1) if vessel.get("course") is not None else None
            ),
            "目的地": destination_label(vessel),
            "吃水 米": vessel.get("draught"),
            "AIS报告时间 UTC": vessel.get("observed_at"),
            "接收时间（迪拜）": reception_time(vessel.get("received_at")),
            "上游接收时间（迪拜）": reception_time(vessel.get("provider_received_at")),
            "数据年龄 分钟": (
                round(vessel["age_minutes"], 1)
                if vessel.get("age_minutes") is not None
                else None
            ),
            "数据年龄依据": vessel.get("age_basis"),
            "来源署名": source_label(vessel),
            "纬度": vessel.get("lat"),
            "经度": vessel.get("lon"),
            "数据源": source_label(vessel),
            "来源": vessel.get("source_url") or AIS.SOURCE,
        }
        for vessel in vessels
    ]


def print_asset_record(asset: dict) -> dict:
    metric_type = str(asset.get("metric_type") or "")
    if daily_output_value(asset) == "未披露" and asset.get("aggregate_references"):
        metric_type = asset["aggregate_references"][0]["metric_type"]
    return {
        "名称": display_name(asset),
        "中文名称": asset.get("name_cn") or asset.get("name"),
        "英文名称": asset.get("name"),
        "国家": asset.get("country"),
        "资产层级": asset.get("asset_level_label"),
        "生产状态": asset.get("operating_status_label"),
        "本层级日产量": daily_output_value(asset),
        "产量显示": production_display_value(asset),
        "合计口径说明": aggregate_production_note(asset),
        "产量口径说明": (
            f"{asset['ownership_basis']}；{asset['note']}"
            if asset["is_daily_output"]
            else ""
        ),
        "其他日量指标": other_daily_metric(asset),
        "指标口径": METRIC_LABELS.get(metric_type, metric_type or "未披露"),
        "数据日期": production_display_date(asset),
        "来源链接": asset.get("source_url"),
        "合计参考证据链接": "；".join(
            row["source_url"] for row in asset.get("aggregate_references", [])
        ),
        "产量检索复核": asset.get("production_review", {}).get("conclusion"),
        "运营商（2026-03目录参考）": asset.get("public_metadata", {}).get("operator"),
        "发现年（目录参考）": asset.get("public_metadata", {}).get("discoveryYear"),
        "商业投产年（目录参考）": asset.get("public_metadata", {}).get(
            "productionStartYear"
        ),
        "GEM Unit ID": asset.get("public_metadata", {}).get("unitId"),
        "参考资料链接": asset.get("public_metadata", {}).get("source_url"),
        "地图坐标精度": asset.get("map_coordinate_precision") or "未核验",
    }
