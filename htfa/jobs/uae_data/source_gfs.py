"""UAE 财政部 GFS 数据源：提取 → 清洗 → 入库 → 回写工作簿。

逻辑源自 scripts/data_sources/gfs/update_gfs.py（整体移植），唯一的介质差异：
- 输入目录从 data/GFS 改为 data/UAE/raw/gfs/；
- 解析结果不再直接写工作簿，而是先入 DuckDB（gfs_quarterly / gfs_annual），
  merge() 再从库查询回写「季度_GFS」「年度_GFS」及「指标字典」。

口径保持与旧脚本 100% 一致：
- 年度值只用原件中年发表列，绝不由季度加总（MOF 明确说明两者可以不同）；
- 没有值的单元格不入库（保留缺失语义），行/列顺序照旧；
- 写工作簿仍采用 ZIP 层 OOXML 补丁（只改目标部件，其余部件字节不变），
  写后逐单元格校验并生成 data/UAE/raw/gfs/validation_report.json。
"""

from __future__ import annotations

import hashlib
import html as html_lib
import io
import json
import os
import re
import sys
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from pypdf import PdfReader

from .paths import DATA_DIR, SCRIPTS_DIR
from ._excel_helpers import cleanup_excel_automation
from ._official_download import download_file, fetch_bytes


from .db import (  # noqa: E402
    connect,
    replace,
    upsert_dictionary_rows,
)

SOURCE_NAME = "UAE Ministry of Finance (MOF GFS)"
UNIT = "百万阿联酋迪拉姆"
UPDATED_AT = date.today().isoformat()
QUARTER_ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
QUARTER_BY_MONTH = {3: 1, 6: 2, 9: 3, 12: 4}
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MARKUP_COMPAT_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_NS = "http://www.w3.org/XML/1998/namespace"

RAW_GFS = DATA_DIR / "raw" / "gfs"
GFS_INDEX_URL = (
    "https://mof.gov.ae/en/public-finance/uae-federal-budget/"
    "government-financial-statistics/"
)
QUARTERLY_TABLE = "gfs_quarterly"
ANNUAL_TABLE = "gfs_annual"

_HTML_HREF_PATTERN = re.compile(
    r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)


def _discover_gfs_files(page_html: str | bytes) -> dict[int, str]:
    """从财政部 GFS 页面发现按年份归档的官方 PDF/XLSX 直链。"""

    if isinstance(page_html, bytes):
        page_html = page_html.decode("utf-8", errors="replace")
    discovered: dict[int, tuple[tuple[int, str], str]] = {}
    for raw_href in _HTML_HREF_PATTERN.findall(page_html):
        href = html_lib.unescape(raw_href).replace("\\/", "/")
        url = urljoin(GFS_INDEX_URL, href)
        parsed = urlparse(url)
        filename = Path(unquote(parsed.path)).name
        suffix = Path(filename).suffix.casefold()
        if suffix not in {".xlsx", ".pdf"}:
            continue
        if not re.match(r"(?i)^gfs(?:[-_ ]|$)", filename):
            continue
        years = re.findall(r"20\d{2}", filename)
        if not years:
            continue
        year = int(years[0])
        # The current XLSX is the machine-readable choice when both formats
        # are advertised for the same release year.
        priority = 0 if suffix == ".xlsx" else 1
        candidate = ((priority, url), url)
        previous = discovered.get(year)
        if previous is None or candidate[0] < previous[0]:
            discovered[year] = candidate
    return {year: value[1] for year, value in discovered.items()}


def _remove_release_variant(year: int, keep_suffix: str) -> None:
    """删除同一年已被新格式替代的精确缓存文件，避免解析重复年份。"""

    for suffix in (".pdf", ".xlsx"):
        if suffix == keep_suffix:
            continue
        path = RAW_GFS / f"GFS-{year}{suffix}"
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _download_releases(*, force: bool = False) -> str:
    """从财政部公开目录刷新最新 GFS 发布文件并返回运行摘要。"""

    page = fetch_bytes(GFS_INDEX_URL, referer=GFS_INDEX_URL)
    discovered = _discover_gfs_files(page)
    if not discovered:
        raise RuntimeError("MOF GFS 页面未发现可识别的 PDF/XLSX 发布文件")

    latest_year = max(discovered)
    downloaded: list[int] = []
    reused: list[int] = []
    for year, url in sorted(discovered.items()):
        suffix = Path(urlparse(url).path).suffix.casefold()
        destination = RAW_GFS / f"GFS-{year}{suffix}"
        status = download_file(
            url,
            destination,
            force=force or year == latest_year,
            min_bytes=1024,
            referer=GFS_INDEX_URL,
        )
        _remove_release_variant(year, suffix)
        (downloaded if status == "downloaded" else reused).append(year)

    detail: list[str] = []
    if downloaded:
        detail.append("刷新 " + ", ".join(f"GFS-{year}" for year in downloaded))
    if reused:
        detail.append("缓存 " + ", ".join(f"GFS-{year}" for year in reused))
    return "MOF GFS 官网：" + "；".join(detail)


@dataclass(frozen=True)
class Indicator:
    """一条 GFS 科目及其目标工作簿元数据。"""

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

# Code 2M 未出现在 2012-2015 源发布中。
OPTIONAL_BY_YEAR = {year: {"2M"} for year in range(2012, 2016)}


# --------------------------------------------------------------------------
# 源文件解析（与 update_gfs.py 完全一致）
# --------------------------------------------------------------------------

def _parse_decimal(value: object) -> Decimal | None:
    """解析官方源数值，避免二进制舍入。"""

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
    """在提取出的 PDF 文本中定位每一条英文 GFS 行标签。"""

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
    """从单页 GFS PDF 提取 Q1-Q4 与年度值。"""

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
        # 早期 PDF 可能把前导负号与数字用空格拆开。
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
    """返回现代 GFS 工作簿中唯一非元数据工作表。"""

    candidates = [
        sheet
        for sheet in workbook.worksheets
        if "meta" not in sheet.title.casefold()
    ]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one non-metadata GFS worksheet")
    return candidates[0]


def extract_excel(path: Path) -> dict[str, tuple[Decimal | None, ...]]:
    """从现代 GFS 工作簿提取 Q1-Q4 与可选的年度值。"""

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
    """提取源目录中全部预期年度发布（2012-2026）。"""

    releases: dict[int, dict[str, tuple[Decimal | None, ...]]] = {}
    source_files = sorted(source_dir.glob("GFS-*.*"))
    for path in source_files:
        match = re.fullmatch(r"GFS-(20\d{2})\.(pdf|xlsx)", path.name)
        if not match:
            continue
        year = int(match.group(1))
        if year in releases:
            raise ValueError(f"Duplicate GFS release year: {year}")
        releases[year] = (
            extract_pdf(path) if path.suffix == ".pdf" else extract_excel(path)
        )
    expected_years = set(range(2012, 2027))
    if set(releases) != expected_years:
        raise ValueError(
            f"Expected releases for 2012-2026; got {sorted(releases)}"
        )
    return releases


def _period_records(
    releases: dict[int, dict[str, tuple[Decimal | None, ...]]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """按季度与年度组织降序目标记录（每条记录含 29 个科目值）。"""

    quarterly: list[dict[str, object]] = []
    annual: list[dict[str, object]] = []
    for year, rows in releases.items():
        for quarter in range(1, 5):
            values = [
                rows.get(indicator.code, (None,) * 5)[quarter - 1]
                for indicator in INDICATORS
            ]
            if any(value is not None for value in values):
                quarterly.append(
                    {
                        "period": f"{year}-{QUARTER_ENDS[quarter]}",
                        "source_file": f"GFS-{year}",
                        "values": values,
                    }
                )
        annual_values = [
            rows.get(indicator.code, (None,) * 5)[4] for indicator in INDICATORS
        ]
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
    """校验已发布的会计恒等式但不改动源值。"""

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


# --------------------------------------------------------------------------
# 记录 → 入库行
# --------------------------------------------------------------------------

def _records_to_db_rows(
    releases: dict[int, dict[str, tuple[Decimal | None, ...]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """把解析结果拆成季度/年度两表的行（无值单元格不入库）。"""

    quarterly_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    for year, rows in sorted(releases.items()):
        for quarter in range(1, 5):
            values = [
                rows.get(indicator.code, (None,) * 5)[quarter - 1]
                for indicator in INDICATORS
            ]
            if any(value is not None for value in values):
                for indicator, value in zip(INDICATORS, values, strict=True):
                    if value is not None:
                        quarterly_rows.append(
                            {
                                "year": year,
                                "quarter": quarter,
                                "indicator": indicator.code,
                                "value": value,
                            }
                        )
        annual_values = [
            rows.get(indicator.code, (None,) * 5)[4] for indicator in INDICATORS
        ]
        if any(value is not None for value in annual_values):
            for indicator, value in zip(INDICATORS, annual_values, strict=True):
                if value is not None:
                    annual_rows.append(
                        {
                            "year": year,
                            "indicator": indicator.code,
                            "value": value,
                        }
                    )
    return quarterly_rows, annual_rows


def _dictionary_rows() -> list[dict[str, object]]:
    """29 个科目 × 季度/年度两个频率 = 58 行指标字典。"""

    rows: list[dict[str, object]] = []
    for label, frequency in (("季度", "季"), ("年度", "年")):
        for indicator in INDICATORS:
            rows.append(
                {
                    "indicator_name": indicator.name.replace(
                        "阿联酋:GFS:", f"阿联酋:GFS:{label}:", 1
                    ),
                    "frequency": frequency,
                    "unit": UNIT,
                    "source": SOURCE_NAME,
                    "type": "金额",
                    "industry": "财政",
                    "updated_at": date.today(),
                }
            )
    return rows


# --------------------------------------------------------------------------
# 工作簿写入（ZIP 层 OOXML 补丁，与 update_gfs.py 一致）
# --------------------------------------------------------------------------

def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _sheet_digest(sheet: object) -> str:
    """对单元格内容/公式哈希，用于证明无关工作表保持不变。"""

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
    """记录 GFS 更新必须保留的用户内容。"""

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
    """构建 Excel COM 写入器消费的 JSON 安全 payload。"""

    def frequency_indicators(label: str) -> list[dict[str, str]]:
        frequency = "季" if label == "季度" else "年"
        return [
            {
                "code": indicator.code,
                "name": indicator.name.replace("阿联酋:GFS:", f"阿联酋:GFS:{label}:", 1),
                "frequency": frequency,
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
    """解析 XML 并保留 Excel 使用的命名空间前缀。"""

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


def _style_with_format(entries: dict[str, bytes], format_code: str) -> str:
    """按格式串在 styles.xml 中找对应 xf 下标（找不到返回 '0'）。

    兼容性说明：旧脚本硬编码样式 ID（16/18/19/6），但 openpyxl 重存工作簿会
    重新编号样式表，硬编码 ID 会错位（Quarter GFS 日期格式校验失败）。
    改用格式码解析，保证与当前工作簿样式表一致。
    """

    styles_root = _parse_xml(entries["xl/styles.xml"])
    fmt_by_id = {
        node.attrib["numFmtId"]: node.attrib["formatCode"]
        for node in styles_root.iter(f"{{{MAIN_NS}}}numFmt")
    }
    xfs = styles_root.find(f"{{{MAIN_NS}}}cellXfs")
    if xfs is None:
        return "0"
    for index, xf in enumerate(xfs.findall(f"{{{MAIN_NS}}}xf")):
        num_fmt_id = xf.attrib.get("numFmtId")
        candidate = fmt_by_id.get(num_fmt_id)
        if candidate == format_code or (
            candidate is not None
            and candidate.replace("\\", "") == format_code.replace("\\", "")
        ):
            return str(index)
    return "0"


def _bold_header_style(entries: dict[str, bytes]) -> str:
    """找第一个使用加粗字体的 xf 下标（表头样式，找不到返回 '0'）。"""

    styles_root = _parse_xml(entries["xl/styles.xml"])
    fonts = styles_root.find(f"{{{MAIN_NS}}}fonts")
    xfs = styles_root.find(f"{{{MAIN_NS}}}cellXfs")
    if fonts is None or xfs is None:
        return "0"
    bold_font_ids = {
        index
        for index, font in enumerate(fonts.findall(f"{{{MAIN_NS}}}font"))
        if font.find(f"{{{MAIN_NS}}}b") is not None
    }
    for index, xf in enumerate(xfs.findall(f"{{{MAIN_NS}}}xf")):
        if int(xf.attrib.get("fontId", "0")) in bold_font_ids:
            return str(index)
    return "0"


def _sheet_style_map(
    entries: dict[str, bytes],
    target: str,
    date_format: str = "yyyy\\-mm\\-dd",
) -> dict[str, str]:
    """收集/推导单个 GFS 工作表的样式 ID（表头/单位/来源/更新时间/日期/数值）。

    优先复用该工作表现有单元格的样式（与被重写前的观感一致）；现有样式为
    General（可能被本脚本此前误写）时，按该表权威的 date_format 回退到
    格式码解析（季度/年度日期列格式不同）。
    """

    fallback = {
        "header": _bold_header_style(entries),
        "unit": "0",
        "source": "0",
        "updated_at": _style_with_format(entries, "yyyy\\-mm\\-dd"),
        "date": _style_with_format(entries, date_format),
        "number": _style_with_format(entries, "#,##0.000"),
    }
    if fallback["date"] == "0":
        fallback["date"] = _style_with_format(entries, "yyyy\\-mm\\-dd")
    if target not in entries:
        return fallback
    root = _parse_xml(entries[target])
    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        return fallback

    style_by_cell: dict[tuple[int, int], str] = {}
    for row in sheet_data.findall(f"{{{MAIN_NS}}}row"):
        row_number = int(row.attrib.get("r", "0"))
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            match = re.fullmatch(r"([A-Z]+)(\d+)", reference)
            if match:
                column = 0
                for char in match.group(1):
                    column = column * 26 + (ord(char) - 64)
                style_by_cell[(row_number, column)] = cell.attrib.get("s", "0")

    def use(row: int, column: int) -> str:
        return style_by_cell.get((row, column)) or fallback

    def valid(row: int, column: int) -> str | None:
        """取现有单元格样式；为 General（'0'）或缺失时视为无效。"""
        style = style_by_cell.get((row, column))
        if style and style != "0":
            return style
        return None

    header = use(2, 1) if (2, 1) in style_by_cell else fallback["header"]
    # 日期/数值优先沿用工作表现有样式（年度_GFS 的日期列是 "yyyy"），
    # 但若现有样式是 General（可能被此前误写污染）则退回格式码解析。
    return {
        "header": header,
        "unit": use(4, 2),
        "source": use(5, 2),
        "updated_at": valid(6, 2) or fallback["updated_at"],
        "date": valid(7, 1) or fallback["date"],
        "number": valid(7, 2) or fallback["number"],
    }


def _build_sheet_xml(
    sheet_spec: dict[str, object], payload: dict[str, object], styles: dict[str, str]
) -> bytes:
    """用现有工作簿样式 ID 构建一个自包含的工作表。"""

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
        style = styles["header"] if row_number == 2 else "0"
        row.append(_inline_cell(f"A{row_number}", metadata_labels[row_number - 2], style))
        for column, indicator in enumerate(indicators, start=2):
            reference = f"{_column_name(column)}{row_number}"
            if row_number == 2:
                row.append(_inline_cell(reference, indicator["name"], styles["header"]))
            elif row_number == 3:
                row.append(_inline_cell(reference, sheet_spec["frequency"]))
            elif row_number == 4:
                row.append(_inline_cell(reference, payload["unit"], styles["unit"]))
            elif row_number == 5:
                row.append(_inline_cell(reference, payload["source"], styles["source"]))
            else:
                row.append(_number_cell(reference, _excel_serial(payload["updated_at"]), styles["updated_at"]))

    for row_number, record in enumerate(records, start=7):
        row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_number), "spans": f"1:{column_count}"})
        row.append(_number_cell(f"A{row_number}", _excel_serial(record["period"]), styles["date"]))
        for column, value in enumerate(record["values"], start=2):
            if value is not None:
                row.append(_number_cell(f"{_column_name(column)}{row_number}", value, styles["number"]))
    return _xml_bytes(root)


def _shared_strings(entries: dict[str, bytes]) -> list[str]:
    # 兼容性说明：openpyxl 保存过的工作簿可能没有 sharedStrings.xml 部件
    # （字符串全部以 inlineStr 存储），此时按空共享串表处理，旧脚本会直接报错。
    if "xl/sharedStrings.xml" not in entries:
        return []
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

    header_row = rows.get(1)
    header_values: dict[str, str | None] = {}
    if header_row is not None:
        for cell in header_row.findall(f"{{{MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            match = re.fullmatch(r"([A-Z]+)1", reference)
            if match:
                header_values[match.group(1)] = _cell_text(cell, shared)
    extended_dictionary = (
        header_values.get("D") == "频率"
        and header_values.get("H") == "数据来源"
    )
    dictionary_columns = (
        ("A", "B", "C", "D", "H")
        if extended_dictionary
        else ("A", "B", "C", "D")
    )
    dictionary_span = "1:9" if extended_dictionary else "1:4"

    template_row = rows[last_data_row]
    styles: dict[str, str | None] = {}
    for column in dictionary_columns:
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
            row = ET.Element(
                f"{{{MAIN_NS}}}row",
                {"r": str(row_number), "spans": dictionary_span},
            )
            rows[row_number] = row
            sheet_data.append(row)
        if extended_dictionary:
            values_by_column = {
                "A": name,
                "B": indicator["type"],
                "C": indicator["industry"],
                "D": indicator.get("frequency", ""),
                "H": indicator["source"],
            }
        else:
            values_by_column = {
                "A": name,
                "B": indicator["type"],
                "C": indicator["industry"],
                "D": indicator["source"],
            }
        for column in dictionary_columns:
            value = values_by_column[column]
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
        last_column = 9 if extended_dictionary else 5
        dimension.set(
            "ref",
            f"A1:{_column_name(last_column)}{max(max(rows), last_data_row)}",
        )
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
    """只补丁必需的 OOXML 部件并原子替换工作簿。"""

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
        styles = _sheet_style_map(entries, target, str(sheet_spec.get("date_format", "yyyy\\-mm\\-dd")))
        entries[target] = _build_sheet_xml(sheet_spec, payload, styles)

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
        # A previous Excel COM writer can finish its PowerShell process before
        # Excel has released the workbook handle.  Reap only hidden automation
        # instances and retry the atomic replacement; a user-visible Excel is
        # never terminated by this path.
        last_error: PermissionError | None = None
        for _attempt in range(4):
            cleanup_excel_automation()
            try:
                os.replace(temp_path, workbook_path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(1.0)
        if last_error is not None:
            raise last_error
    finally:
        temp_path.unlink(missing_ok=True)


def validate_target(
    workbook_path: Path,
    payload: dict[str, object],
    before: dict[str, object],
) -> dict[str, object]:
    """重新打开已保存的工作簿，逐项核对数值、格式与保留的工作表。"""

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
        updated_dictionary_names = {
            item["name"] for item in payload["indicators"]
        }
        dictionary = workbook["指标字典"]
        for row_number, expected_row in enumerate(prior_dictionary, start=1):
            if expected_row and expected_row[0] in (
                removable_dictionary_names | updated_dictionary_names
            ):
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
    """生成简洁、机器可读的 QA 报告。"""

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


# --------------------------------------------------------------------------
# 事务上下文
# --------------------------------------------------------------------------

@contextmanager
def _transaction(con):
    """显式事务上下文（BEGIN/COMMIT/ROLLBACK）。

    注意：duckdb 1.5.5 的 con.begin() 上下文管理器在退出时会关闭连接，
    与 update_data.py 在同一连接上继续 log_run 的约定冲突，因此自行管理事务。
    """

    con.execute("BEGIN TRANSACTION")
    try:
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


# --------------------------------------------------------------------------
# 库查询 → 记录（merge 的输入）
# --------------------------------------------------------------------------

def _query_records(con) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """从库中重建旧脚本结构（29 值行、降序），供 build_payload 使用。"""

    quarterly_by_period: dict[str, dict[str, Decimal | None]] = {}
    for year, quarter, indicator, value in con.execute(
        f"SELECT year, quarter, indicator, value FROM {QUARTERLY_TABLE}"
    ).fetchall():
        period = f"{year}-{QUARTER_ENDS[int(quarter)]}"
        quarterly_by_period.setdefault(period, {})[indicator] = value
    annual_by_period: dict[str, dict[str, Decimal | None]] = {}
    for year, indicator, value in con.execute(
        f"SELECT year, indicator, value FROM {ANNUAL_TABLE}"
    ).fetchall():
        period = f"{year}-12-31"
        annual_by_period.setdefault(period, {})[indicator] = value

    def records(mapping: dict[str, dict[str, Decimal | None]]) -> list[dict[str, object]]:
        result = []
        for period in sorted(mapping, reverse=True):
            value_by_code = mapping[period]
            values = [
                value_by_code.get(indicator.code) for indicator in INDICATORS
            ]
            result.append(
                {
                    "period": period,
                    "source_file": f"GFS-{int(period[:4])}",
                    "values": values,
                }
            )
        return result

    return records(quarterly_by_period), records(annual_by_period)


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------

def update(
    con, *, force: bool = False, skip_download: bool = False
) -> dict[str, object]:
    """抓取/发现输入 → 解析清洗 → 事务内入库。

    返回 {"status", "rows", "note"}；异常直接抛出由总控记录。
    """

    source_dir = RAW_GFS
    download_note = ""
    if not skip_download:
        try:
            download_note = _download_releases(force=force)
        except (OSError, RuntimeError) as exc:
            # A temporary outage must not discard a previously validated local
            # release. Parsing still runs and reports the fallback in the note.
            if not any(source_dir.glob("GFS-*.*")):
                raise
            download_note = f"MOF GFS 官网发现失败，使用本地缓存（{exc}）"
    releases = extract_sources(source_dir)
    quarterly_rows, annual_rows = _records_to_db_rows(releases)
    with _transaction(con):
        replace(con, QUARTERLY_TABLE, quarterly_rows)
        replace(con, ANNUAL_TABLE, annual_rows)
        upsert_dictionary_rows(con, _dictionary_rows())
    quarterly, annual = _period_records(releases)
    report = build_validation_report(source_dir, quarterly, annual, None)
    (source_dir / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = len(quarterly_rows) + len(annual_rows)
    note = (
        f"GFS 2012-2026 提取入库：季度 {len(quarterly)} 期 × 29 科目，"
        f"年度 {len(annual)} 期 × 29 科目，共 {total} 个有效值"
    )
    if download_note:
        note += f"；{download_note}"
    return {
        "status": "ok",
        "rows": total,
        "note": note,
    }


def merge(workbook_path: Path) -> dict[str, object]:
    """从库查询 GFS 数据，按旧脚本协议写「季度_GFS」「年度_GFS」与指标字典。

    工作簿写入前自动快照，写后逐单元格校验，全部通过才保留结果。
    """

    target = Path(workbook_path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Workbook not found: {target}")
    con = connect(read_only=True)
    try:
        quarterly, annual = _query_records(con)
    finally:
        con.close()
    payload = build_payload(quarterly, annual)
    before = snapshot_workbook(target)
    write_workbook(target, payload)
    target_checks = validate_target(target, payload, before)
    report = build_validation_report(RAW_GFS, quarterly, annual, target_checks)
    (RAW_GFS / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "status": "ok",
        "note": (
            f"季度_GFS {len(quarterly)} 期 + 年度_GFS {len(annual)} 期已回写，"
            f"校验通过（逐格检查 {target_checks['target_cells_checked']} 个单元格）"
        ),
    }


if __name__ == "__main__":
    # 自检提示（不执行网络/工作簿写入）
    _releases = extract_sources(RAW_GFS)
    _quarterly, _annual = _period_records(_releases)
    _q_rows, _a_rows = _records_to_db_rows(_releases)
    print(
        f"[source_gfs] 自检：2012-2026 源文件解析成功，"
        f"季度 {len(_quarterly)} 期 / 年度 {len(_annual)} 期；"
        f"可入库值 {len(_q_rows) + len(_a_rows)} 个。"
    )
    print("[source_gfs] 运行 htfa.jobs.uae_data.update_data --source gfs 执行入库；"
          "htfa.jobs.uae_data.merge_workbook --source gfs 回写工作簿。")
