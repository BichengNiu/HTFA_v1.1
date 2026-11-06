"""Publish energy monitoring report indicators from collected DuckDB facts.

Collection is owned exclusively by ``htfa.jobs.energy_supply.publish``.
Monthly PortWatch series describe sums of observed days, never full-month
estimates. Source daily records, geometry and individual AIS observations stay
in the energy schema and remain available through the original download UI.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from htfa.monitoring.energy_supply.processing.workbook_reporting import (
    build_report_indicators,
)
from . import db
from .workbook_sheet_writer import write_indicator_sheets

SHEETS = {
    "ports": "月度_能源港口",
    "chokepoints": "月度_能源通道",
    "ais": "月度_能源船舶",
}
SOURCE = "IMF PortWatch；已观测日期合计，不代表完整月份"


def update(con, *, force=False, skip_download=False) -> dict:
    """Derive workbook-facing series from already collected source facts."""
    rows, metadata = build_report_indicators(con)
    with db.transaction(con):
        con.execute(
            "CREATE TABLE IF NOT EXISTS energy_supply.report_indicators ("
            "kind VARCHAR, period DATE, indicator VARCHAR, value DOUBLE, "
            "unit VARCHAR, source VARCHAR, PRIMARY KEY(period,indicator))"
        )
        con.execute("DELETE FROM energy_supply.report_indicators")
        con.executemany(
            "INSERT INTO energy_supply.report_indicators VALUES (?,?,?,?,?,?)", rows
        )
        db.upsert_dictionary_rows(con, metadata.values())
    return {"status": "ok", "rows": len(rows), "note": "能源报告指标已从库内事实重建"}


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
                metadata[indicator] = {
                    "frequency": "月",
                    "unit": unit,
                    "source": source,
                }
            specs.append(
                {
                    "name": sheet,
                    "title": f"能源保供：{sheet[5:]}",
                    "indicators": sorted(metadata),
                    "metadata": metadata,
                    "rows": list(values.items()),
                }
            )
    if not specs:
        raise ValueError("能源报告指标尚未发布")
    counts = write_indicator_sheets(workbook_path, specs)
    return {"status": "ok", "rows": sum(counts.values()), "note": str(counts)}
