"""Extract UAE Ministry of Finance GFS releases and update the UAE workbook.

The source releases contain quarterly observations and a separately published
annual value.  Annual values are never reconstructed from quarterly values,
because the Ministry of Finance explicitly notes that the two may differ.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from pypdf import PdfReader


SOURCE_NAME = "UAE Ministry of Finance (MOF GFS)"
UNIT = "百万阿联酋迪拉姆"
UPDATED_AT = date.today().isoformat()
QUARTER_ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MARKUP_COMPAT_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_NS = "http://www.w3.org/XML/1998/namespace"


@dataclass(frozen=True)
class Indicator:
    """One GFS line item and its target-workbook metadata."""

    code: str
    name: str
    source_label: str


INDICATORS = (
    Indicator("1", "阿联酋:GFS:收入", r"Revenue"),
    Indicator("11", "阿联酋:GFS:收入:税收", r"Taxes"),
    Indicator("12", "阿联酋:GFS:收入:社会缴款", r"Social contributions"),
    Indicator("13", "阿联酋:GFS:收入:赠款", r"Grants"),
    Indicator("14", "阿联酋:GFS:收入:其他收入", r"Other revenue"),
    Indicator("2", "阿联酋:GFS:费用", r"Expense"),
    Indicator("21", "阿联酋:GFS:费用:雇员报酬", r"Compensation of employees"),
    Indicator("22", "阿联酋:GFS:费用:商品和服务使用", r"Use of goods and services"),
    Indicator("23", "阿联酋:GFS:费用:固定资本消耗", r"Consumption of fixed capital"),
    Indicator("24", "阿联酋:GFS:费用:利息", r"Interest"),
    Indicator("25", "阿联酋:GFS:费用:补贴", r"Subsidies"),
    Indicator("26", "阿联酋:GFS:费用:赠款", r"Grants"),
    Indicator("27", "阿联酋:GFS:费用:社会福利", r"Social benefits"),
    Indicator("28", "阿联酋:GFS:费用:其他费用", r"Other expense"),
    Indicator("GOB", "阿联酋:GFS:总营业余额", r"Gross operating balance"),
    Indicator("NOB", "阿联酋:GFS:净营业余额", r"Net operating balance"),
    Indicator(
        "31",
        "阿联酋:GFS:非金融资产净投资",
        r"(?:Net Acquisition of Nonfinancial Assets|"
        r"Net/gross investment in nonfinancial assets)",
    ),
    Indicator("311", "阿联酋:GFS:非金融资产净投资:固定资产", r"Fixed assets"),
    Indicator(
        "312",
        "阿联酋:GFS:非金融资产净投资:存货",
        r"(?:Change in inventories|Inventories)",
    ),
    Indicator("313", "阿联酋:GFS:非金融资产净投资:贵重物品", r"Valuables"),
    Indicator("314", "阿联酋:GFS:非金融资产净投资:非生产资产", r"Nonproduced assets"),
    Indicator("2M", "阿联酋:GFS:支出", r"Expenditure"),
    Indicator("NLB", "阿联酋:GFS:净贷款或净借款", r"Net lending / borrowing"),
    Indicator("32", "阿联酋:GFS:金融资产净获得", r"Net acquisition of financial assets"),
    Indicator("321", "阿联酋:GFS:金融资产净获得:境内债务人", r"(?:Domestic debtors|Domestic)"),
    Indicator("322", "阿联酋:GFS:金融资产净获得:境外债务人", r"(?:External debtors|Foreign)"),
    Indicator("33", "阿联酋:GFS:负债净发生", r"Net incurrence of liabilities"),
    Indicator("331", "阿联酋:GFS:负债净发生:境内债权人", r"(?:Domestic creditors|Domestic)"),
    Indicator("332", "阿联酋:GFS:负债净发生:境外债权人", r"(?:External creditors|Foreign)"),
)

INDICATOR_BY_CODE = {indicator.code: indicator for indicator in INDICATORS}
NUMBER_BODY = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
NUMBER_PATTERN = re.compile(
    rf"\(\s*{NUMBER_BODY}\s*\)|-{NUMBER_BODY}|{NUMBER_BODY}|(?<!\S)-(?!\S)"
)

# Code 2M did not appear in the 2012-2015 source releases.
OPTIONAL_BY_YEAR = {year: {"2M"} for year in range(2012, 2016)}


def _parse_decimal(value: object) -> Decimal | None:
    """Parse an official source value without introducing binary rounding."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        token = value.strip().replace("\u2212", "-").replace("\u2013", "-")
        if not token or token.casefold() in {"na", "n/a", "-"}:
            return None if token.casefold() in {"na", "n/a", ""} else Decimal(0)
        negative = token.startswith("(") and token.endswith(")")
        if negative:
            token = token[1:-1].strip()
        token = token.replace(",", "")
        try:
            result = Decimal(token)
        except InvalidOperation as exc:
            raise ValueError(f"Not a numeric GFS value: {value!r}") from exc
        return -result if negative else result
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Not a numeric GFS value: {value!r}") from exc


def _pdf_row_starts(text: str) -> list[tuple[int, int, Indicator]]:
    """Locate each English GFS row label in extracted PDF text."""

    starts: list[tuple[int, int, Indicator]] = []
    for indicator in INDICATORS:
        pattern = re.compile(
            rf"(?<!\w){re.escape(indicator.code)}\s+{indicator.source_label}\b",
            re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous PDF row {indicator.code}: found {len(matches)} matches"
            )
        if matches:
            match = matches[0]
            starts.append((match.start(), match.end(), indicator))
    return sorted(starts, key=lambda item: item[0])


def extract_pdf(path: Path) -> dict[str, tuple[Decimal, ...]]:
    """Extract Q1-Q4 and annual values from one single-page GFS PDF."""

    reader = PdfReader(path)
    if len(reader.pages) != 1:
        raise ValueError(f"Expected one-page GFS PDF: {path.name}")
    text = reader.pages[0].extract_text() or ""
    text = text.replace("\u2212", "-").replace("\u2013", "-")
    text = " ".join(text.split())
    starts = _pdf_row_starts(text)
    year = int(path.stem.rsplit("-", 1)[-1])
    found_codes = {item[2].code for item in starts}
    required_codes = set(INDICATOR_BY_CODE) - OPTIONAL_BY_YEAR.get(year, set())
    missing = sorted(required_codes - found_codes)
    if missing:
        raise ValueError(f"{path.name}: missing GFS rows {missing}")

    rows: dict[str, tuple[Decimal, ...]] = {}
    for index, (_, start, indicator) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        segment = text[start:stop]
        # Some older PDFs split a leading minus from its number with spaces.
        segment = re.sub(rf"-[ \t]+(?={NUMBER_BODY})", "-", segment)
        tokens = NUMBER_PATTERN.findall(segment)
        if len(tokens) < 5:
            raise ValueError(
                f"{path.name}: row {indicator.code} has {len(tokens)} values, expected 5"
            )
        values = tuple(_parse_decimal(token) for token in tokens[:5])
        if any(value is None for value in values):
            raise ValueError(f"{path.name}: unexpected NA in row {indicator.code}")
        rows[indicator.code] = values  # type: ignore[assignment]
    return rows


def _source_sheet(workbook: object):
    """Return the non-metadata worksheet from a modern GFS workbook."""

    candidates = [
        sheet
        for sheet in workbook.worksheets
        if "meta" not in sheet.title.casefold()
    ]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one non-metadata GFS worksheet")
    return candidates[0]


def extract_excel(path: Path) -> dict[str, tuple[Decimal | None, ...]]:
    """Extract Q1-Q4 and optional annual values from a modern GFS workbook."""

    year = int(path.stem.rsplit("-", 1)[-1])
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = _source_sheet(workbook)
        rows: dict[str, tuple[Decimal | None, ...]] = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_code = row[0]
            if isinstance(raw_code, float) and raw_code.is_integer():
                code = str(int(raw_code))
            else:
                code = str(raw_code).strip() if raw_code is not None else ""
            if code not in INDICATOR_BY_CODE:
                continue
            values = [_parse_decimal(value) for value in row[2:6]]
            annual = _parse_decimal(row[6]) if len(row) > 6 else None
            rows[code] = (*values, annual)
    finally:
        workbook.close()

    required_codes = set(INDICATOR_BY_CODE) - OPTIONAL_BY_YEAR.get(year, set())
    missing = sorted(required_codes - set(rows))
    if missing:
        raise ValueError(f"{path.name}: missing GFS rows {missing}")
    return rows


def extract_sources(source_dir: Path) -> dict[int, dict[str, tuple[Decimal | None, ...]]]:
    """Extract all expected annual releases in the source directory."""

    releases: dict[int, dict[str, tuple[Decimal | None, ...]]] = {}
    source_files = sorted(source_dir.glob("GFS-*.*"))
    for path in source_files:
        match = re.fullmatch(r"GFS-(20\d{2})\.(pdf|xlsx)", path.name)
        if not match:
            continue
        year = int(match.group(1))
        if year in releases:
            raise ValueError(f"Duplicate GFS release year: {year}")
        releases[year] = extract_pdf(path) if path.suffix == ".pdf" else extract_excel(path)
    expected_years = set(range(2012, 2027))
    if set(releases) != expected_years:
        raise ValueError(
            f"Expected releases for 2012-2026; got {sorted(releases)}"
        )
    return releases


def _period_records(
    releases: dict[int, dict[str, tuple[Decimal | None, ...]]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build descending quarterly and annual target records."""

    quarterly: list[dict[str, object]] = []
    annual: list[dict[str, object]] = []
    for year, rows in releases.items():
        for quarter in range(1, 5):
            values = [rows.get(indicator.code, (None,) * 5)[quarter - 1] for indicator in INDICATORS]
            if any(value is not None for value in values):
                quarterly.append(
                    {
                        "period": f"{year}-{QUARTER_ENDS[quarter]}",
                        "source_file": f"GFS-{year}",
                        "values": values,
                    }
                )
        annual_values = [rows.get(indicator.code, (None,) * 5)[4] for indicator in INDICATORS]
        if any(value is not None for value in annual_values):
            annual.append(
                {
                    "period": f"{year}-12-31",
                    "source_file": f"GFS-{year}",
                    "values": annual_values,
                }
            )
    quarterly.sort(key=lambda record: str(record["period"]), reverse=True)
    annual.sort(key=lambda record: str(record["period"]), reverse=True)
    return quarterly, annual


IDENTITIES = (
    ("revenue_components", "1", ("11", "12", "13", "14"), 1),
    ("expense_components", "2", ("21", "22", "23", "24", "25", "26", "27", "28"), 1),
    ("gross_operating_balance", "GOB", ("1", "2", "23"), (1, -1, 1)),
    ("net_operating_balance", "NOB", ("1", "2"), (1, -1)),
    ("nonfinancial_assets", "31", ("311", "312", "313", "314"), 1),
    ("expenditure", "2M", ("2", "31"), 1),
    ("net_lending_borrowing", "NLB", ("1", "2", "31"), (1, -1, -1)),
    ("financial_assets", "32", ("321", "322"), 1),
    ("liabilities", "33", ("331", "332"), 1),
)


def _identity_findings(
    records: Iterable[dict[str, object]], frequency: str, tolerance: Decimal = Decimal("1")
) -> tuple[int, list[dict[str, object]]]:
    """Check published accounting identities without altering source values."""

    checks = 0
    findings: list[dict[str, object]] = []
    for record in records:
        value_by_code = dict(
            zip((indicator.code for indicator in INDICATORS), record["values"], strict=True)
        )
        for name, target_code, component_codes, signs in IDENTITIES:
            target = value_by_code[target_code]
            components = [value_by_code[code] for code in component_codes]
            if target is None or any(value is None for value in components):
                continue
            checks += 1
            multipliers = (
                (signs,) * len(component_codes) if isinstance(signs, int) else signs
            )
            calculated = sum(
                (value * sign for value, sign in zip(components, multipliers, strict=True)),
                Decimal(0),
            )
            difference = target - calculated
            if abs(difference) > tolerance:
                findings.append(
                    {
                        "frequency": frequency,
                        "period": record["period"],
                        "check": name,
                        "published": str(target),
                        "calculated": str(calculated),
                        "difference": str(difference),
                        "severity": "source_caveat",
                    }
                )
    return checks, findings


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _sheet_digest(sheet: object) -> str:
    """Hash cell values/formulas to prove unrelated sheets remain unchanged."""

    digest = hashlib.sha256()
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            payload = json.dumps(
                [cell.coordinate, _json_value(cell.value), cell.data_type],
                ensure_ascii=False,
                sort_keys=True,
            )
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def snapshot_workbook(path: Path) -> dict[str, object]:
    """Capture user content that the GFS update must preserve."""

    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=True)
    try:
        ignored = {"季度_GFS", "年度_GFS", "指标字典"}
        digests = {
            sheet.title: _sheet_digest(sheet)
            for sheet in workbook.worksheets
            if sheet.title not in ignored
        }
        dictionary = workbook["指标字典"]
        dictionary_values = [
            tuple(_json_value(value) for value in row)
            for row in dictionary.iter_rows(values_only=True)
        ]
        while dictionary_values and not any(
            value is not None for value in dictionary_values[-1]
        ):
            dictionary_values.pop()
        snapshot = {
            "sheet_names": workbook.sheetnames,
            "digests": digests,
            "dictionary_values": dictionary_values,
        }
    finally:
        workbook.close()
    with zipfile.ZipFile(path) as archive:
        snapshot["package_digests"] = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
        }
    return snapshot


def build_payload(
    quarterly: list[dict[str, object]], annual: list[dict[str, object]]
) -> dict[str, object]:
    """Build the JSON-safe payload consumed by the Excel COM writer."""

    def frequency_indicators(label: str) -> list[dict[str, str]]:
        return [
            {
                "code": indicator.code,
                "name": indicator.name.replace("阿联酋:GFS:", f"阿联酋:GFS:{label}:", 1),
                "type": "金额",
                "industry": "财政",
                "source": SOURCE_NAME,
            }
            for indicator in INDICATORS
        ]

    quarterly_indicators = frequency_indicators("季度")
    annual_indicators = frequency_indicators("年度")

    def json_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                **record,
                "values": [_json_value(value) for value in record["values"]],
            }
            for record in records
        ]

    return {
        "updated_at": UPDATED_AT,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "dictionary_sheet_name": "指标字典",
        "indicators": [*quarterly_indicators, *annual_indicators],
        "remove_dictionary_indicators": [indicator.name for indicator in INDICATORS],
        "sheets": [
            {
                "name": "季度_GFS",
                "frequency": "季",
                "date_format": "yyyy\\-mm\\-dd",
                "indicators": quarterly_indicators,
                "records": json_records(quarterly),
            },
            {
                "name": "年度_GFS",
                "frequency": "年",
                "date_format": "yyyy",
                "indicators": annual_indicators,
                "records": json_records(annual),
            },
        ],
        "unit": UNIT,
        "source": SOURCE_NAME,
    }


def _parse_xml(data: bytes) -> ET.Element:
    """Parse XML while retaining the namespace prefixes used by Excel."""

    for _, namespace in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        prefix, uri = namespace
        if prefix != "xml" and not re.fullmatch(r"ns\d+", prefix or ""):
            ET.register_namespace(prefix, uri)
    return ET.fromstring(data)


def _xml_bytes(root: ET.Element) -> bytes:
    ignorable_key = f"{{{MARKUP_COMPAT_NS}}}Ignorable"
    ignorable = root.attrib.get(ignorable_key)
    if ignorable:
        used_uris = {
            name[1:].split("}", 1)[0]
            for element in root.iter()
            for name in (element.tag, *element.attrib)
            if isinstance(name, str) and name.startswith("{")
        }
        prefix_to_uri = {
            prefix: uri for uri, prefix in ET._namespace_map.items()  # type: ignore[attr-defined]
        }
        retained = [
            prefix
            for prefix in ignorable.split()
            if prefix_to_uri.get(prefix) in used_uris
        ]
        if retained:
            root.set(ignorable_key, " ".join(retained))
        else:
            root.attrib.pop(ignorable_key, None)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _column_name(number: int) -> str:
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _inline_cell(reference: str, value: str, style: str | None = None) -> ET.Element:
    attributes = {"r": reference, "t": "inlineStr"}
    if style is not None:
        attributes["s"] = style
    cell = ET.Element(f"{{{MAIN_NS}}}c", attributes)
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ET.SubElement(
        inline,
        f"{{{MAIN_NS}}}t",
        {f"{{{XML_NS}}}space": "preserve"},
    )
    text.text = value
    return cell


def _number_cell(reference: str, value: object, style: str) -> ET.Element:
    cell = ET.Element(f"{{{MAIN_NS}}}c", {"r": reference, "s": style})
    node = ET.SubElement(cell, f"{{{MAIN_NS}}}v")
    node.text = str(value)
    return cell


def _excel_serial(period: str) -> int:
    observed = datetime.strptime(period, "%Y-%m-%d").date()
    return (observed - date(1899, 12, 30)).days


def _build_sheet_xml(sheet_spec: dict[str, object], payload: dict[str, object]) -> bytes:
    """Build a self-contained worksheet using existing workbook style IDs."""

    records = sheet_spec["records"]
    indicators = sheet_spec["indicators"]
    row_count = len(records) + 6
    column_count = len(indicators) + 1
    last_column = _column_name(column_count)

    root = ET.Element(f"{{{MAIN_NS}}}worksheet")
    ET.SubElement(root, f"{{{MAIN_NS}}}dimension", {"ref": f"A1:{last_column}{row_count}"})
    views = ET.SubElement(root, f"{{{MAIN_NS}}}sheetViews")
    view = ET.SubElement(views, f"{{{MAIN_NS}}}sheetView", {"workbookViewId": "0"})
    ET.SubElement(
        view,
        f"{{{MAIN_NS}}}pane",
        {"ySplit": "6", "topLeftCell": "A7", "activePane": "bottomLeft", "state": "frozen"},
    )
    ET.SubElement(view, f"{{{MAIN_NS}}}selection", {"pane": "bottomLeft", "activeCell": "A7", "sqref": "A7"})
    ET.SubElement(root, f"{{{MAIN_NS}}}sheetFormatPr", {"defaultRowHeight": "14.25"})
    columns = ET.SubElement(root, f"{{{MAIN_NS}}}cols")
    ET.SubElement(columns, f"{{{MAIN_NS}}}col", {"min": "1", "max": "1", "width": "13.625", "customWidth": "1"})
    ET.SubElement(columns, f"{{{MAIN_NS}}}col", {"min": "2", "max": str(column_count), "width": "33.625", "customWidth": "1"})
    sheet_data = ET.SubElement(root, f"{{{MAIN_NS}}}sheetData")

    row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": "1", "spans": f"1:{column_count}"})
    row.append(_inline_cell("A1", "MOF GFS"))
    metadata_labels = payload["metadata_labels"]
    for row_number in range(2, 7):
        row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_number), "spans": f"1:{column_count}"})
        label_style = "16" if row_number == 2 else None
        row.append(_inline_cell(f"A{row_number}", metadata_labels[row_number - 2], label_style))
        for column, indicator in enumerate(indicators, start=2):
            reference = f"{_column_name(column)}{row_number}"
            if row_number == 2:
                row.append(_inline_cell(reference, indicator["name"], "16"))
            elif row_number == 3:
                row.append(_inline_cell(reference, sheet_spec["frequency"]))
            elif row_number == 4:
                row.append(_inline_cell(reference, payload["unit"]))
            elif row_number == 5:
                row.append(_inline_cell(reference, payload["source"]))
            else:
                row.append(_number_cell(reference, _excel_serial(payload["updated_at"]), "19"))

    date_style = "19" if sheet_spec["frequency"] == "季" else "6"
    for row_number, record in enumerate(records, start=7):
        row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_number), "spans": f"1:{column_count}"})
        row.append(_number_cell(f"A{row_number}", _excel_serial(record["period"]), date_style))
        for column, value in enumerate(record["values"], start=2):
            if value is not None:
                row.append(_number_cell(f"{_column_name(column)}{row_number}", value, "18"))
    return _xml_bytes(root)


def _shared_strings(entries: dict[str, bytes]) -> list[str]:
    root = _parse_xml(entries["xl/sharedStrings.xml"])
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _cell_text(cell: ET.Element, shared: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        value = cell.find(f"{{{MAIN_NS}}}v")
        return shared[int(value.text)] if value is not None and value.text else None
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    return value.text if value is not None else None


def _update_dictionary_xml(data: bytes, entries: dict[str, bytes], payload: dict[str, object]) -> bytes:
    root = _parse_xml(data)
    shared = _shared_strings(entries)
    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        raise ValueError("Indicator dictionary has no sheetData")
    rows = {int(row.attrib["r"]): row for row in sheet_data.findall(f"{{{MAIN_NS}}}row")}
    remove_names = set(payload.get("remove_dictionary_indicators", []))
    for row_number, row in list(rows.items()):
        first = next((cell for cell in row.findall(f"{{{MAIN_NS}}}c") if cell.attrib.get("r") == f"A{row_number}"), None)
        if first is not None and _cell_text(first, shared) in remove_names:
            sheet_data.remove(row)
            del rows[row_number]
    names: dict[str, int] = {}
    last_data_row = 1
    for row_number, row in rows.items():
        first = next((cell for cell in row.findall(f"{{{MAIN_NS}}}c") if cell.attrib.get("r") == f"A{row_number}"), None)
        if first is not None:
            value = _cell_text(first, shared)
            if value:
                names[value] = row_number
                last_data_row = max(last_data_row, row_number)

    template_row = rows[last_data_row]
    styles: dict[str, str | None] = {}
    for column in "ABCD":
        cell = next((item for item in template_row.findall(f"{{{MAIN_NS}}}c") if item.attrib.get("r") == f"{column}{last_data_row}"), None)
        styles[column] = cell.attrib.get("s") if cell is not None else None

    for indicator in payload["indicators"]:
        name = indicator["name"]
        row_number = names.get(name)
        if row_number is None:
            last_data_row += 1
            row_number = last_data_row
            names[name] = row_number
        row = rows.get(row_number)
        if row is None:
            row = ET.Element(f"{{{MAIN_NS}}}row", {"r": str(row_number), "spans": "1:4"})
            rows[row_number] = row
            sheet_data.append(row)
        values = (name, indicator["type"], indicator["industry"], indicator["source"])
        for column, value in zip("ABCD", values, strict=True):
            reference = f"{column}{row_number}"
            for old_cell in list(row.findall(f"{{{MAIN_NS}}}c")):
                if old_cell.attrib.get("r") == reference:
                    row.remove(old_cell)
            row.append(_inline_cell(reference, value, styles[column]))
        row[:] = sorted(
            row,
            key=lambda cell: re.match(r"[A-Z]+", cell.attrib.get("r", "ZZZ")).group(),
        )

    sheet_data[:] = sorted(sheet_data, key=lambda row: int(row.attrib.get("r", "0")))
    dimension = root.find(f"{{{MAIN_NS}}}dimension")
    if dimension is not None:
        dimension.set("ref", f"A1:G{max(max(rows), last_data_row)}")
    return _xml_bytes(root)


def _sheet_targets(workbook_root: ET.Element, rels_root: ET.Element) -> dict[str, str]:
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    result: dict[str, str] = {}
    sheets = workbook_root.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        raise ValueError("Workbook has no sheets collection")
    for sheet in sheets:
        target = rel_targets[sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]].lstrip("/")
        result[sheet.attrib["name"]] = target if target.startswith("xl/") else f"xl/{target}"
    return result


def write_workbook(workbook_path: Path, payload: dict[str, object]) -> None:
    """Patch only the required OOXML parts and atomically replace the workbook."""

    with zipfile.ZipFile(workbook_path, "r") as source:
        infos = source.infolist()
        entries = {info.filename: source.read(info.filename) for info in infos}
    workbook_root = _parse_xml(entries["xl/workbook.xml"])
    rels_root = _parse_xml(entries["xl/_rels/workbook.xml.rels"])
    content_root = _parse_xml(entries["[Content_Types].xml"])
    targets = _sheet_targets(workbook_root, rels_root)
    dictionary_target = targets["指标字典"]
    entries[dictionary_target] = _update_dictionary_xml(
        entries[dictionary_target], entries, payload
    )

    sheets_node = workbook_root.find(f"{{{MAIN_NS}}}sheets")
    existing_sheet_ids = [int(sheet.attrib["sheetId"]) for sheet in sheets_node]
    existing_rel_ids = [
        int(match.group(1))
        for rel in rels_root
        if (match := re.fullmatch(r"rId(\d+)", rel.attrib["Id"]))
    ]
    existing_file_ids = [
        int(match.group(1))
        for name in entries
        if (match := re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", name))
    ]
    next_sheet_id = max(existing_sheet_ids) + 1
    next_rel_id = max(existing_rel_ids) + 1
    next_file_id = max(existing_file_ids) + 1

    for sheet_spec in payload["sheets"]:
        sheet_name = sheet_spec["name"]
        target = targets.get(sheet_name)
        if target is None:
            target = f"xl/worksheets/sheet{next_file_id}.xml"
            rel_id = f"rId{next_rel_id}"
            ET.SubElement(
                sheets_node,
                f"{{{MAIN_NS}}}sheet",
                {"name": sheet_name, "sheetId": str(next_sheet_id), f"{{{OFFICE_REL_NS}}}id": rel_id},
            )
            ET.SubElement(
                rels_root,
                f"{{{PACKAGE_REL_NS}}}Relationship",
                {
                    "Id": rel_id,
                    "Type": f"{OFFICE_REL_NS}/worksheet",
                    "Target": target.removeprefix("xl/"),
                },
            )
            ET.SubElement(
                content_root,
                f"{{{CONTENT_TYPE_NS}}}Override",
                {
                    "PartName": f"/{target}",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
                },
            )
            targets[sheet_name] = target
            next_sheet_id += 1
            next_rel_id += 1
            next_file_id += 1
        entries[target] = _build_sheet_xml(sheet_spec, payload)

    entries["xl/workbook.xml"] = _xml_bytes(workbook_root)
    entries["xl/_rels/workbook.xml.rels"] = _xml_bytes(rels_root)
    entries["[Content_Types].xml"] = _xml_bytes(content_root)

    temp_path = workbook_path.with_name(
        f".{workbook_path.name}.gfs-{uuid.uuid4().hex}.tmp"
    )
    try:
        with zipfile.ZipFile(temp_path, "w") as destination:
            original_names = set()
            for info in infos:
                original_names.add(info.filename)
                destination.writestr(info, entries[info.filename])
            for name in sorted(set(entries) - original_names):
                destination.writestr(name, entries[name], compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temp_path, "r") as check:
            bad_entry = check.testzip()
            if bad_entry:
                raise ValueError(f"Corrupt generated XLSX entry: {bad_entry}")
        os.replace(temp_path, workbook_path)
    finally:
        temp_path.unlink(missing_ok=True)


def validate_target(
    workbook_path: Path,
    payload: dict[str, object],
    before: dict[str, object],
) -> dict[str, object]:
    """Reopen the saved workbook and compare values, formats, and preserved sheets."""

    with zipfile.ZipFile(workbook_path) as archive:
        current_package = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
        }
        namespace_issues: list[tuple[str, list[str]]] = []
        for name in archive.namelist():
            if not name.endswith((".xml", ".vml")):
                continue
            xml_text = archive.read(name).decode("utf-8", errors="ignore")
            root_tag = re.search(r"<[^!?][^>]*>", xml_text)
            if root_tag is None:
                continue
            ignorable = re.search(
                r"(?:mc:)?Ignorable=[\"']([^\"']+)[\"']",
                root_tag.group(0),
            )
            if ignorable is None:
                continue
            declared = set(
                re.findall(r"xmlns:([A-Za-z0-9_]+)=", root_tag.group(0))
            )
            missing = sorted(set(ignorable.group(1).split()) - declared)
            if missing:
                namespace_issues.append((name, missing))
        if namespace_issues:
            raise ValueError(
                f"Invalid mc:Ignorable namespace declarations: {namespace_issues}"
            )
        workbook_root = _parse_xml(archive.read("xl/workbook.xml"))
        rels_root = _parse_xml(archive.read("xl/_rels/workbook.xml.rels"))
        sheet_targets = _sheet_targets(workbook_root, rels_root)
    allowed_changes = {
        "[Content_Types].xml",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        sheet_targets["指标字典"],
        sheet_targets["季度_GFS"],
        sheet_targets["年度_GFS"],
    }
    prior_package = before["package_digests"]
    for name, prior_digest in prior_package.items():
        if name not in current_package:
            raise ValueError(f"Existing XLSX package part was removed: {name}")
        if name not in allowed_changes and current_package[name] != prior_digest:
            raise ValueError(f"Unrelated XLSX package part changed: {name}")
    unexpected_new_parts = set(current_package) - set(prior_package) - allowed_changes
    if unexpected_new_parts:
        raise ValueError(f"Unexpected XLSX package parts added: {sorted(unexpected_new_parts)}")

    workbook = load_workbook(
        workbook_path, read_only=False, data_only=False, keep_links=True
    )
    checked_cells = 0
    try:
        for title, expected_digest in before["digests"].items():
            actual_digest = _sheet_digest(workbook[title])
            if actual_digest != expected_digest:
                raise ValueError(f"Unrelated worksheet changed: {title}")

        prior_dictionary = before["dictionary_values"]
        removable_dictionary_names = set(
            payload.get("remove_dictionary_indicators", [])
        )
        dictionary = workbook["指标字典"]
        for row_number, expected_row in enumerate(prior_dictionary, start=1):
            if expected_row and expected_row[0] in removable_dictionary_names:
                continue
            actual_row = tuple(
                _json_value(dictionary.cell(row_number, column).value)
                for column in range(1, len(expected_row) + 1)
            )
            if actual_row != expected_row:
                raise ValueError(
                    f"Existing indicator dictionary row changed: {row_number}"
                )

        all_indicator_names = [item["name"] for item in payload["indicators"]]
        for sheet_spec in payload["sheets"]:
            indicator_names = [item["name"] for item in sheet_spec["indicators"]]
            sheet = workbook[sheet_spec["name"]]
            expected_rows = sheet_spec["records"]
            if sheet.max_row != len(expected_rows) + 6:
                raise ValueError(f"Unexpected row count in {sheet.title}")
            if sheet.max_column != len(indicator_names) + 1:
                raise ValueError(f"Unexpected column count in {sheet.title}")
            if sheet.cell(2, 1).value != "指标名称":
                raise ValueError(f"Invalid metadata header in {sheet.title}")
            if sheet.cell(2, 2).value != indicator_names[0]:
                raise ValueError(f"Invalid indicator order in {sheet.title}")
            if sheet.cell(7, 1).number_format != sheet_spec["date_format"]:
                raise ValueError(f"Invalid date format in {sheet.title}")
            if sheet.cell(7, 2).number_format != "#,##0.000":
                raise ValueError(f"Invalid number format in {sheet.title}")

            for row_offset, record in enumerate(expected_rows, start=7):
                expected_date = datetime.strptime(record["period"], "%Y-%m-%d").date()
                actual_date = sheet.cell(row_offset, 1).value
                if isinstance(actual_date, datetime):
                    actual_date = actual_date.date()
                if actual_date != expected_date:
                    raise ValueError(
                        f"Date mismatch in {sheet.title}!A{row_offset}: "
                        f"{actual_date!r} != {expected_date!r}"
                    )
                for column, expected in enumerate(record["values"], start=2):
                    actual = sheet.cell(row_offset, column).value
                    if expected is None:
                        if actual is not None:
                            raise ValueError(
                                f"Expected blank in {sheet.title}!{sheet.cell(row_offset, column).coordinate}"
                            )
                    else:
                        if actual is None or abs(Decimal(str(actual)) - Decimal(expected)) > Decimal("0.0000001"):
                            raise ValueError(
                                f"Value mismatch in {sheet.title}!{sheet.cell(row_offset, column).coordinate}"
                            )
                    checked_cells += 1

        dictionary_names = {
            dictionary.cell(row, 1).value
            for row in range(2, dictionary.max_row + 1)
            if dictionary.cell(row, 1).value
        }
        missing_indicators = sorted(set(all_indicator_names) - dictionary_names)
        if missing_indicators:
            raise ValueError(
                f"Indicators missing from dictionary: {missing_indicators}"
            )
        stale_indicators = sorted(removable_dictionary_names & dictionary_names)
        if stale_indicators:
            raise ValueError(
                f"Stale frequency-ambiguous indicators remain: {stale_indicators}"
            )
    finally:
        workbook.close()
    return {
        "target_cells_checked": checked_cells,
        "preserved_sheets_checked": len(before["digests"]),
        "package_parts_byte_preserved": len(current_package) - len(allowed_changes),
        "format_checks": "passed",
        "namespace_checks": "passed",
        "dictionary_checks": "passed",
    }


def build_validation_report(
    source_dir: Path,
    quarterly: list[dict[str, object]],
    annual: list[dict[str, object]],
    target_checks: dict[str, object] | None,
) -> dict[str, object]:
    """Create a concise, machine-readable QA report."""

    quarter_checks, quarter_findings = _identity_findings(quarterly, "quarterly")
    annual_checks, annual_findings = _identity_findings(annual, "annual")
    values_extracted = sum(
        value is not None
        for record in [*quarterly, *annual]
        for value in record["values"]
    )
    return {
        "status": "passed" if target_checks is not None else "source_validation_passed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_directory": str(source_dir),
        "source_files": [
            path.name
            for path in sorted(source_dir.glob("GFS-*.*"))
            if path.suffix.casefold() in {".pdf", ".xlsx"}
        ],
        "source_file_count": 15,
        "quarterly_periods": len(quarterly),
        "annual_periods": len(annual),
        "gfs_line_items": len(INDICATORS),
        "workbook_indicator_series": len(INDICATORS) * 2,
        "numeric_values_extracted": values_extracted,
        "accounting_identity_checks": quarter_checks + annual_checks,
        "published_identity_caveats": quarter_findings + annual_findings,
        "caveat_note": (
            "Values are reproduced as published. The official releases state that "
            "cumulative quarterly data need not equal independently published annual data."
        ),
        "target_validation": target_checks,
    }


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        default=repo_root / "data" / "阿联酋.xlsx",
        help="Destination workbook (default: data/阿联酋.xlsx)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate source extraction without modifying the destination workbook",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[2]
    source_dir = repo_root / "data" / "GFS"
    workbook_path = args.workbook.resolve()

    releases = extract_sources(source_dir)
    quarterly, annual = _period_records(releases)
    payload = build_payload(quarterly, annual)
    target_checks: dict[str, object] | None = None

    if not args.validate_only:
        if not workbook_path.exists():
            raise FileNotFoundError(workbook_path)
        before = snapshot_workbook(workbook_path)
        write_workbook(workbook_path, payload)
        target_checks = validate_target(workbook_path, payload, before)

    report = build_validation_report(
        source_dir, quarterly, annual, target_checks
    )
    report_path = source_dir / "validation_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"GFS update failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
