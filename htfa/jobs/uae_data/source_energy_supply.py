"""Publish energy monitoring report indicators from collected DuckDB facts.

Collection is owned exclusively by ``htfa.jobs.energy_supply.publish``.
Monthly PortWatch series describe sums of observed days, never full-month
estimates. Source daily records, geometry and individual AIS observations stay
in the energy schema and remain available through the original download UI.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import calendar
import json
import math
from pathlib import Path

from . import db
from .workbook_sheet_writer import write_indicator_sheets
from htfa.monitoring.energy_supply.portwatch_records import (
    PORT_METRICS, CHOKE_METRICS, EXPORT_SHIP_LABELS,
)
from htfa.monitoring.energy_supply.entity_names import display_name

SHEETS = {"ports": "月度_能源港口", "chokepoints": "月度_能源通道", "ais": "月度_能源船舶"}
SOURCE = "IMF PortWatch；已观测日期合计，不代表完整月份"


def _metric_label(field: str) -> tuple[str, str]:
    for prefix, label, unit in (
        ("portcalls", "进港次数", "艘次"), ("import", "进口估算货量", "公吨"),
        ("export", "出口估算货量", "公吨"), ("n_total", "通过次数", "艘次"),
        ("n", "通过次数", "艘次"), ("capacity", "承载能力", "载重吨"),
    ):
        if field == prefix:
            return label, unit
        if field.startswith(prefix + "_"):
            return EXPORT_SHIP_LABELS[field[len(prefix) + 1:]] + label, unit
    raise ValueError(f"未知能源指标：{field}")


def update(con, *, force=False, skip_download=False) -> dict:
    """Derive workbook-facing series from already collected source facts."""
    catalogs = {
        (kind, identifier): json.loads(payload)
        for kind, identifier, payload in con.execute(
            "SELECT kind,id,payload FROM energy_supply.catalogs "
            "WHERE kind IN ('ports','chokepoints')"
        ).fetchall()
    }
    rows, metadata = [], {}
    for kind, fields in (("ports", PORT_METRICS), ("chokepoints", CHOKE_METRICS)):
        # Stream source JSON in bounded batches. A lateral json_each join over
        # the complete history can exhaust memory on local/cloud runtimes.
        monthly = {}
        cursor = con.execute(
            "SELECT day,node_id,payload FROM energy_supply.portwatch_daily WHERE kind=?",
            [kind],
        )
        while batch := cursor.fetchmany(2000):
            for day, node, payload in batch:
                period = day.replace(day=calendar.monthrange(day.year, day.month)[1])
                record = json.loads(payload)
                for field in fields:
                    total = monthly.setdefault((period, node, field), [0.0, True])
                    value = record.get(field)
                    if value is None:
                        total[1] = False
                    elif not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
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
    ais = con.execute("""
        SELECT last_day(CAST(observed AT TIME ZONE 'UTC' AS DATE)),
               coalesce(json_extract_string(payload,'$.region'),'未知水域'),
               count(DISTINCT mmsi)
        FROM energy_supply.ais_reports GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    for period, region, value in ais:
        name = f"能源保供:{region}:月内已观测去重船数"
        source = "Open Waters AIS；稀疏观测样本，不代表全部通行量"
        rows.append(("ais", period, name, value, "艘", source))
        metadata[name] = _metadata(name, "艘", source)
    if not rows:
        raise ValueError("能源保供没有可发布的观测指标")
    with db.transaction(con):
        con.execute("CREATE TABLE IF NOT EXISTS energy_supply.report_indicators ("
                    "kind VARCHAR, period DATE, indicator VARCHAR, value DOUBLE, "
                    "unit VARCHAR, source VARCHAR, PRIMARY KEY(period,indicator))")
        con.execute("DELETE FROM energy_supply.report_indicators")
        con.executemany("INSERT INTO energy_supply.report_indicators VALUES (?,?,?,?,?,?)", rows)
        db.upsert_dictionary_rows(con, metadata.values())
    return {"status": "ok", "rows": len(rows), "note": "能源报告指标已从库内事实重建"}


def _metadata(name, unit, source):
    return {"indicator_name": name, "frequency": "月", "unit": unit,
            "source": source, "type": "已观测量", "industry": "能源保供",
            "updated_at": datetime.now()}


def merge(workbook_path: Path, *, database: Path | None = None) -> dict:
    """Rebuild only energy-owned workbook sheets from the unified database."""
    specs = []
    with db.connect(database, read_only=True) as con:
        for kind, sheet in SHEETS.items():
            records = con.execute(
                "SELECT period,indicator,value,unit,source "
                "FROM energy_supply.report_indicators WHERE kind=? ORDER BY period,indicator",
                [kind],
            ).fetchall()
            if not records:
                continue
            values, metadata = defaultdict(dict), {}
            for period, indicator, value, unit, source in records:
                values[period][indicator] = value
                metadata[indicator] = {"frequency": "月", "unit": unit, "source": source}
            specs.append({"name": sheet, "title": f"能源保供：{sheet[5:]}",
                          "indicators": sorted(metadata), "metadata": metadata,
                          "rows": list(values.items())})
    if not specs:
        raise ValueError("能源报告指标尚未发布")
    counts = write_indicator_sheets(workbook_path, specs)
    return {"status": "ok", "rows": sum(counts.values()), "note": str(counts)}
