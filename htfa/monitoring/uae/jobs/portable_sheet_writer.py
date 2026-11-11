"""Linux OOXML equivalent of the four source-owned Excel COM writers."""

from calendar import monthrange
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def write_payload_sheet(helper_name, workbook_path, payload_path, sheet_name):
    """Validate a source payload and atomically replace only its owned sheet."""
    defaults = {
        "write_indicator_sheet.ps1": None,
        "write_cbuae_sheet.ps1": ("#,##0.000", 34),
        "write_baker_hughes_sheet.ps1": ("#,##0", 23),
        "write_uae_pmi_sheet.ps1": ("0.0", 38),
    }
    if helper_name not in defaults:
        raise ValueError(f"Unsupported Excel helper: {helper_name}")
    path = Path(workbook_path)
    if (path.parent / f"~${path.name}").exists():
        raise RuntimeError("请先关闭 Excel 工作簿")
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    is_pmi = helper_name == "write_uae_pmi_sheet.ps1"
    indicators = [payload["indicator"]] if is_pmi else payload["indicators"]
    names = [item["name"] for item in indicators]
    if not names or len(names) != len(set(names)) or not payload["records"]:
        raise ValueError("Empty or duplicate source indicators/records")
    if defaults[helper_name] is None:
        number_format = payload["number_format"]
        width = float(payload["column_width"])
        period_format = payload["period_format"]
    else:
        number_format, width = defaults[helper_name]
        period_format = "month"
    if not number_format or width <= 0 or period_format not in {"month", "day"}:
        raise ValueError("Invalid source sheet format")
    updated = datetime.strptime(payload["updated_at"], "%Y-%m-%d")
    records, periods = [], set()
    for record in payload["records"]:
        stamp = datetime.strptime(record["period"], "%Y-%m-%d" if period_format == "day" else "%Y-%m")
        if period_format == "month":
            stamp = stamp.replace(day=monthrange(stamp.year, stamp.month)[1])
        if stamp in periods:
            raise ValueError(f"Duplicate source period: {stamp}")
        periods.add(stamp)
        values = [record["value"]] if is_pmi else record["values"]
        if len(values) != len(names):
            raise ValueError("Source record width differs from indicator count")
        records.append([stamp, *[None if v is None else float(v) for v in values]])
    workbook = load_workbook(path, keep_links=True)
    temporary = None
    try:
        dictionary = workbook[payload["dictionary_sheet_name"]]
        position = workbook.sheetnames.index(sheet_name) if sheet_name in workbook.sheetnames else len(workbook.sheetnames)
        if sheet_name in workbook.sheetnames:
            workbook.remove(workbook[sheet_name])
        sheet = workbook.create_sheet(sheet_name, position)
        title = "Baker Hughes" if helper_name == "write_baker_hughes_sheet.ps1" else payload.get("source_label", payload["source"])
        sheet.append([title])
        labels = payload["metadata_labels"]
        if len(labels) != 5:
            raise ValueError("Source payload must have five metadata rows")
        for index, label in enumerate(labels):
            sheet.append([label, *[
                (item["name"], payload["frequency"], item.get("unit", payload.get("unit")), payload["source"], updated)[index]
                for item in indicators
            ]])
        for record in records:
            sheet.append(record)
        for cell in sheet[2]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.alignment = Alignment(horizontal="center")
        sheet.column_dimensions["A"].width = 13
        for column in range(2, len(names) + 2):
            sheet.column_dimensions[get_column_letter(column)].width = width
            sheet.cell(6, column).number_format = "yyyy-mm-dd"
        for row in sheet.iter_rows(min_row=7):
            row[0].number_format = "yyyy-mm-dd" if period_format == "day" else "yyyy-mm"
            for cell in row[1:]:
                cell.number_format = number_format
        known = {}
        for row in range(2, dictionary.max_row + 1):
            name = dictionary.cell(row, 1).value
            if name in names and is_pmi and name in known:
                raise ValueError(f"Duplicate indicator dictionary entry: {name}")
            known[name] = row
        for item in indicators:
            row = known.get(item["name"])
            if row is None:
                row = dictionary.max_row + 1
                dictionary.cell(row, 1, item["name"])
                known[item["name"]] = row
            elif not is_pmi:
                continue
            dictionary.cell(row, 2, item["type"])
            dictionary.cell(row, 3, item["industry"])
            if is_pmi or helper_name == "write_baker_hughes_sheet.ps1":
                dictionary.cell(row, 4, payload["source"])
        with tempfile.NamedTemporaryFile(prefix=".source-sheet-", suffix=".tmp.xlsx", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        workbook.save(temporary)
        os.replace(temporary, path)
    finally:
        workbook.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
