"""Validated OOXML writers for temporary cloud-publication workbooks only."""

from calendar import monthrange
import csv
from datetime import date
import json
import math
from pathlib import Path
import subprocess

import pandas as pd
from openpyxl import Workbook

from htfa.monitoring.uae.database import published_source
from . import db
from .uae_metadata import sync_workbook_dictionary
from .workbook_sheet_writer import write_indicator_sheets, read_indicator_metadata


def materialize_report(database: Path, destination: Path):
    """Seed every sheet from the latest published DB, never a stale tracked Excel."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    try:
        with published_source(database).open() as tables:
            for name in tables.sheet_names:
                sheet = workbook.create_sheet(name)
                raw = tables.parse(sheet_name=name, header=None)
                for row in raw.itertuples(index=False, name=None):
                    sheet.append([None if pd.isna(value) else value for value in row])
        workbook.save(destination)
    finally:
        workbook.close()


def _number(value):
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite workbook observation")
    return result


def _period(value, daily=False):
    if daily:
        return date.fromisoformat(value)
    year, month = map(int, value.split("-"))
    return date(year, month, monthrange(year, month)[1])


def write_payload(workbook_path, payload_path, sheet_name):
    """Preserve per-column units, nulls and dates from existing writer payloads."""
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    indicators = payload.get("indicators") or [payload["indicator"]]
    names = [item["name"] for item in indicators]
    if not names or len(names) != len(set(names)):
        raise ValueError("Empty or duplicated indicator headers")
    frequency = payload["frequency"]
    if frequency not in {"日", "日度", "月", "月度"}:
        raise ValueError(f"Unsupported payload frequency: {frequency}")
    daily = payload.get("period_format") == "day" or frequency in {"日", "日度"}
    rows, periods = [], set()
    for record in payload["records"]:
        period = _period(record["period"], daily)
        values = record.get("values", [record.get("value")])
        if len(values) != len(names) or period in periods:
            raise ValueError("Payload record width mismatch or duplicate period")
        periods.add(period)
        rows.append((period, dict(zip(names, map(_number, values), strict=True))))
    metadata = {item["name"]: {"frequency": frequency,
                "unit": item.get("unit", payload.get("unit", "")), "source": payload["source"]}
                for item in indicators}
    write_indicator_sheets(Path(workbook_path), [{
        "name": sheet_name, "title": payload.get("source_label", payload["source"]),
        "indicators": names, "metadata": metadata, "rows": rows,
    }])
    # PMI verifies its dictionary immediately; keep that contract before returning.
    sync_workbook_dictionary(Path(workbook_path))


def run_csv_writer(arguments):
    """Implement only the two known CSV→Excel contracts; reject other commands."""
    args = list(map(str, arguments))
    script = Path(args[args.index("-File") + 1]).resolve()
    if script.parent != Path(__file__).resolve().parent:
        raise ValueError("Portable writer requires a repository-owned helper")
    def option(name):
        return args[args.index(name) + 1]
    workbook = Path(option("-WorkbookPath"))
    if script.name == "merge_workbook.ps1":
        sheet_name, path, daily = "月度_MEsteel", Path(option("-WideCsvPath")), True
    elif script.name == "merge_dld_indices_into_uae_workbook.ps1":
        sheet_name, path, daily = option("-SheetName"), Path(option("-CsvPath")), True
    else:
        raise ValueError(f"No portable counterpart for {script.name}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        names = header[1:]
        rows = []
        seen = set()
        for row in reader:
            period = _period(row[0], daily)
            if len(row) != len(header) or period in seen:
                raise ValueError("CSV width mismatch or duplicate period")
            seen.add(period)
            rows.append((period, dict(zip(names, map(_number, row[1:]), strict=True))))
    with db.connect(read_only=True) as con:
        metadata = read_indicator_metadata(con, names)
    write_indicator_sheets(workbook, [{"name": sheet_name, "title": sheet_name,
        "indicators": names, "metadata": metadata, "rows": rows}])
    sync_workbook_dictionary(workbook)
    return subprocess.CompletedProcess(tuple(args), 0, "Portable OOXML merge verified", "")
