"""Observed monthly energy series; no workbook or database mutations."""

import calendar
import math
from datetime import datetime

from htfa.monitoring.energy_supply.contracts.records import (
    CHOKE_METRICS,
    EXPORT_SHIP_LABELS,
    PORT_METRICS,
)
from htfa.monitoring.energy_supply.data import report_repository as repository
from htfa.monitoring.energy_supply.processing.entity_names import display_name

SOURCE = "IMF PortWatch；已观测日期合计，不代表完整月份"


def _metric_label(field: str) -> tuple[str, str]:
    for prefix, label, unit in (
        ("portcalls", "进港次数", "艘次"),
        ("import", "进口估算货量", "公吨"),
        ("export", "出口估算货量", "公吨"),
        ("n_total", "通过次数", "艘次"),
        ("n", "通过次数", "艘次"),
        ("capacity", "承载能力", "载重吨"),
    ):
        if field == prefix:
            return label, unit
        if field.startswith(prefix + "_"):
            return EXPORT_SHIP_LABELS[field[len(prefix) + 1 :]] + label, unit
    raise ValueError(f"未知能源指标：{field}")


def _metadata(name, unit, source):
    return {
        "indicator_name": name,
        "frequency": "月",
        "unit": unit,
        "source": source,
        "type": "已观测量",
        "industry": "能源保供",
        "updated_at": datetime.now(),
    }


def build_report_indicators(con):
    """Derive workbook-facing series from already collected source facts."""
    catalogs = repository.node_catalogs(con)
    rows, metadata = [], {}
    for kind, fields in (("ports", PORT_METRICS), ("chokepoints", CHOKE_METRICS)):
        # Stream source JSON in bounded batches. A lateral json_each join over
        # the complete history can exhaust memory on local/cloud runtimes.
        monthly = {}
        for day, node, record in repository.daily_observations(con, kind):
            period = day.replace(day=calendar.monthrange(day.year, day.month)[1])
            for field in fields:
                total = monthly.setdefault((period, node, field), [0.0, True])
                value = record.get(field)
                if value is None:
                    total[1] = False
                elif (
                    not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise ValueError(f"非法能源观测值：{kind}/{node}/{day}/{field}")
                else:
                    total[0] += value
        for (period, node, field), (total, valid) in sorted(monthly.items()):
            value = total if valid else None
            catalog = catalogs.get((kind, node))
            if catalog is None:
                raise ValueError(f"能源节点缺少目录：{kind}/{node}")
            label, unit = _metric_label(field)
            name = f"能源保供:{display_name(catalog)}[{node}]:{label}:已观测月合计"
            rows.append((kind, period, name, value, unit, SOURCE))
            metadata[name] = _metadata(name, unit, SOURCE)
    ais = repository.monthly_observed_vessels(con)
    for period, region, value in ais:
        name = f"能源保供:{region}:月内已观测去重船数"
        source = "Open Waters AIS；稀疏观测样本，不代表全部通行量"
        rows.append(("ais", period, name, value, "艘", source))
        metadata[name] = _metadata(name, "艘", source)
    if not rows:
        raise ValueError("能源保供没有可发布的观测指标")
    return rows, metadata
