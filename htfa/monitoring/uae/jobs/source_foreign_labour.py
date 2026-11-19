"""Collect and publish the two displayed labour-flow series for the UAE.

Nepal approvals include re-entry; Bangladesh observations are country
clearances. Preserve source-period checks, missing values and prior history.
"""

from __future__ import annotations

import calendar
import html
import json
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from htfa.monitoring.uae.processing.temporal import calendar_month_end
from . import db
from .db import transaction
from .paths import DATA_DIR

RAW_DIR = DATA_DIR / "raw" / "foreign_labour"

MANIFEST_PATH = RAW_DIR / "manifest.json"

SHEET_NAME = "月度_外籍劳动力"

DOFE_ROOT = "https://dofe.gov.np"

DOFE_MONTHLY_URL = f"{DOFE_ROOT}/category/monthly/"

BMET_OEP_URL = "https://www.oep.gov.bd/reports/country-clearance"

UAE_OEP_COUNTRY_ID = 188

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

NEPAL_MONTHS = {
    "वैशाख": 1,
    "बैशाख": 1,
    "जेष्ठ": 2,
    "जेठ": 2,
    "अषाढ": 3,
    "असार": 3,
    "श्रावण": 4,
    "साउन": 4,
    "भाद्र": 5,
    "भदौ": 5,
    "असोज": 6,
    "आश्विन": 6,
    "कार्तिक": 7,
    "कात्तिक": 7,
    "मंसिर": 8,
    "मङ्सिर": 8,
    "पौष": 9,
    "पुष": 9,
    "माघ": 10,
    "फागुन": 11,
    "चैत": 12,
    "चैत्र": 12,
}

ACTIVE_SERIES = {
    "nepal_with_reentry": ("尼泊尔_DoFE批准_含再入境", "尼泊尔 DoFE monthly final labour approval"),
    "bangladesh_clearance": ("孟加拉国_BMET出境许可", "孟加拉国 BMET/OEP Country Clearance"),
}


def build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            ),
            "Accept": "*/*",
        }
    )
    return session


def get_bytes(session: requests.Session, url: str) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=(30, 240))
            response.raise_for_status()
            return response.content, response.headers.get("Content-Type", "")
        except (requests.ConnectionError, requests.Timeout) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def save_download(
    session: requests.Session,
    url: str,
    destination: Path,
    expected_magic: bytes,
    refresh: bool,
) -> None:
    if destination.exists() and not refresh:
        return
    content, content_type = get_bytes(session, url)
    if not content.startswith(expected_magic):
        preview = content[:100].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Unexpected response for {url}: {content_type}; {preview!r}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def discover_nepal_reports(session: requests.Session) -> list[dict[str, Any]]:
    reports: dict[tuple[int, int], dict[str, Any]] = {}
    for page in range(1, 8):
        response = session.get(DOFE_MONTHLY_URL, params={"page": page}, timeout=90)
        if response.status_code == 404 and page > 1:
            break
        response.raise_for_status()
        matches = list(
            re.finditer(
                r'<h3[^>]*class="[^"]*card__title[^"]*"[^>]*>\s*'
                r'<a[^>]+href="\s*([^"]+?)\s*"[^>]*>(.*?)</a>',
                response.text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )
        found = 0
        for match in matches:
            title = strip_tags(match.group(2))
            parsed = re.search(
                r"([०-९]{4})\s+(\S+)\s+महिनाको\s+श्रम\s+स्वीकृति\s+विवरण",
                title,
            )
            if not parsed:
                progress = re.fullmatch(r"(\S+)\s+महिनाको\s+प्रगति\s+विवरण", title)
                if not progress:
                    continue
                # New monthly reports omit the year from their title. Read
                # the publication's BS year from this card's date, not the
                # site's global current-date banner.
                card_tail = response.text[match.end():]
                card_tail = card_tail.split('<div class="grid__card">', 1)[0]
                year_match = re.search(r"post__date.*?([०-९]{4})", card_tail, re.S)
                if year_match is None:
                    raise RuntimeError(f"DoFE monthly progress report has no publication year: {title}")
                year = int(year_match.group(1).translate(DEVANAGARI_DIGITS))
                month_name = progress.group(1)
            else:
                year = int(parsed.group(1).translate(DEVANAGARI_DIGITS))
                month_name = parsed.group(2)
            month = NEPAL_MONTHS.get(month_name)
            if month is None:
                raise RuntimeError(f"Unknown Nepal month name: {month_name}")
            reports[(year, month)] = {
                "bs_year": year,
                "bs_month": month,
                "title": title,
                "detail_url": urljoin(DOFE_ROOT, match.group(1).strip()),
            }
            found += 1
        if not found:
            break

    for record in reports.values():
        response = session.get(record["detail_url"], timeout=90)
        response.raise_for_status()
        match = re.search(
            r'https://giwmscdnone\.gov\.np/media/pdf_upload/[^"\']+?\.pdf',
            response.text,
            flags=re.IGNORECASE,
        )
        if not match:
            raise RuntimeError(f"PDF link not found: {record['detail_url']}")
        record["url"] = html.unescape(match.group(0))
    return [reports[key] for key in sorted(reports)]


def download_nepal(
    session: requests.Session, refresh: bool
) -> list[dict[str, Any]]:
    directory = RAW_DIR / "nepal"
    results = []
    for record in discover_nepal_reports(session):
        destination = directory / (
            f"nepal_dofe_{record['bs_year']}_{record['bs_month']:02d}.pdf"
        )
        save_download(session, record["url"], destination, b"%PDF", refresh)
        results.append(
            {**record, "path": str(destination.relative_to(DATA_DIR))}
        )
    return results


def iter_complete_months(start_year: int, start_month: int):
    today = date.today()
    final_year = today.year if today.month > 1 else today.year - 1
    final_month = today.month - 1 if today.month > 1 else 12
    year, month = start_year, start_month
    while (year, month) <= (final_year, final_month):
        yield year, month
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


def download_bangladesh(
    session: requests.Session, refresh: bool
) -> list[dict[str, Any]]:
    directory = RAW_DIR / "bangladesh"
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
    for year, month in iter_complete_months(2023, 7):
        destination = directory / f"bangladesh_bmet_{year}_{month:02d}.json"
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        params = {
            "draw": 1,
            "start": 0,
            "length": 100,
            "approval_date_from": start.isoformat(),
            "approval_date_to": end.isoformat(),
            "country_id": UAE_OEP_COUNTRY_ID,
            "gender_id": "",
            "category_id": "",
            "all_skills": 0,
        }
        if not destination.exists() or refresh:
            response = session.get(
                BMET_OEP_URL, params=params, headers=headers, timeout=90
            )
            response.raise_for_status()
            payload = response.json()
            if "payload" not in payload:
                raise RuntimeError(
                    f"Unexpected OEP response for {year}-{month:02d}"
                )
            temporary = destination.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(destination)
            time.sleep(0.1)
        results.append(
            {
                "year": year,
                "month": month,
                "url": BMET_OEP_URL,
                "query": params,
                "path": str(destination.relative_to(DATA_DIR)),
            }
        )
    return results


def download_all(refresh: bool = False) -> None:
    session = build_session()
    manifest: dict[str, Any] = {
        "downloaded_on": date.today().isoformat(),
        "sources": {},
    }
    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["sources"].update({name: data for name, data in existing.get("sources", {}).items()
                                    if name in {"nepal", "bangladesh"}})
    from curl_cffi import requests as browser_requests

    with browser_requests.Session(impersonate="chrome") as nepal_session:
        manifest["sources"]["nepal"] = download_nepal(nepal_session, refresh)
    manifest["sources"]["bangladesh"] = download_bangladesh(session, refresh)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def numeric(value: Any) -> int:
    if value in (None, "", "-"):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return int(str(value).replace(",", "").strip())


def parse_nepal() -> dict[str, dict[str, Any]]:
    monthly: dict[str, dict[str, Any]] = {}
    date_pattern = re.compile(
        r"from\s+(\d{4})-(\d{2})-(\d{2})\s+to\s+"
        r"(\d{4})-(\d{2})-(\d{2})",
        flags=re.IGNORECASE,
    )
    for path in sorted((RAW_DIR / "nepal").glob("*.pdf")):
        reader = PdfReader(path)
        page_texts = [page.extract_text() or "" for page in reader.pages]
        if not any(text.strip() for text in page_texts):
            raise RuntimeError(f"No extractable text in DoFE PDF: {path}")
        text = "\n".join(page_texts)
        dates = date_pattern.search(text)
        if not dates:
            raise RuntimeError(f"Report date range not found: {path}")
        end = date(*map(int, dates.groups()[3:]))
        uae_line = next(
            (
                line.strip()
                for line in text.splitlines()
                if re.match(
                    r"^\d+\s+UAE\s+", line.strip(), flags=re.IGNORECASE
                )
            ),
            None,
        )
        if not uae_line:
            raise RuntimeError(f"UAE row not found: {path}")
        values = [int(value) for value in re.findall(r"\d+", uae_line)][1:]
        if len(values) != 21:
            raise RuntimeError(
                f"Expected 21 DoFE measures in {path.name}, found {len(values)}"
            )
        with_reentry = values[17]
        without_reentry = values[20]
        if with_reentry < without_reentry:
            raise RuntimeError(f"Invalid DoFE re-entry totals in {path.name}")
        key = f"{end.year}-{end.month:02d}"
        if key in monthly:
            raise RuntimeError(f"Multiple DoFE periods assigned to {key}")
        monthly[key] = {
            "with_reentry": with_reentry,
            "without_reentry": without_reentry,
            "period_end": end.isoformat(),
        }
    return monthly


def parse_bangladesh() -> dict[str, int]:
    monthly: dict[str, int] = {}
    for path in sorted((RAW_DIR / "bangladesh").glob("*.json")):
        match = re.search(r"_(\d{4})_(\d{2})\.json$", path.name)
        if not match:
            continue
        year, month = map(int, match.groups())
        payload = json.loads(path.read_text(encoding="utf-8")).get(
            "payload", {}
        )
        rows = payload.get("data", [])
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected one UAE OEP row in {path.name}, got {len(rows)}"
            )
        row = rows[0]
        if "EMIRATES" not in str(row.get("country_name", "")).upper():
            raise RuntimeError(f"Unexpected OEP country in {path.name}: {row}")
        value = numeric(row.get("total_employee"))
        if numeric(payload.get("totalEmployee")) != value:
            raise RuntimeError(f"OEP total mismatch in {path.name}")
        monthly[f"{year}-{month:02d}"] = value
    return monthly


def _rows_to_long(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Store only observed values of the two displayed country series."""
    validate_display_rows(rows)
    return [
        {"period": row["date"], "series": series, "value": row[series], "quality_flag": None}
        for row in rows for series in ACTIVE_SERIES if row.get(series) is not None
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（按需）→ 解析 → 事务内入库 foreign_labour_monthly。"""

    if not skip_download:
        # Monthly files and API responses may be revised behind stable names;
        # online mode must refresh them, while skip_download stays offline.
        download_all(refresh=True)
    rows = build_display_rows()
    long_rows = _rows_to_long(rows)
    with transaction(con):
        db.merge_observations(con, "foreign_labour_monthly", long_rows, ("period", "series"))
        validate_display_rows(_rows_from_db(con))
    note = f"{len(long_rows)} 条序列观测（{rows[-1]['date']} 至 {rows[0]['date']}）"
    return {"status": "ok", "rows": len(long_rows), "note": note}


def _rows_from_db(con) -> list[dict[str, Any]]:
    """Read archived observations; missing country-months remain missing."""
    records = con.execute(
        "SELECT period,series,value FROM foreign_labour_monthly "
        "WHERE series IN ('nepal_with_reentry','bangladesh_clearance')"
    ).fetchall()
    by_period = defaultdict(dict)
    for period, series, value in records:
        by_period[period][series] = value
    return [{"date": period, **{series: values.get(series) for series in ACTIVE_SERIES}}
            for period, values in sorted(by_period.items(), reverse=True)]


def build_display_rows() -> list[dict[str, Any]]:
    """Parse only the two displayed countries; DMW and three-country proxies retire."""
    nepal, bangladesh = parse_nepal(), parse_bangladesh()
    if not nepal or not bangladesh:
        raise ValueError("Displayed labour source is empty: Nepal or Bangladesh")
    rows = []
    for month in sorted(set(nepal) | set(bangladesh), reverse=True):
        year, number = map(int, month.split("-"))
        rows.append({
            "date": calendar_month_end(year, number),
            "nepal_with_reentry": nepal.get(month, {}).get("with_reentry"),
            "bangladesh_clearance": bangladesh.get(month),
        })
    validate_display_rows(rows)
    return rows


def validate_display_rows(rows) -> None:
    """Retain date, missingness and nonnegative whole-person checks."""
    import math

    dates = [row["date"] for row in rows]
    if not dates or dates != sorted(set(dates), reverse=True):
        raise ValueError("Labour dates must be unique and newest first")
    for row in rows:
        for series in ACTIVE_SERIES:
            value = row.get(series)
            if value is not None and (not math.isfinite(value) or value < 0 or int(value) != value):
                raise ValueError(f"Invalid displayed labour value: {series}/{row['date']}")


def merge(workbook_path: Path) -> dict:
    """Publish the two displayed labour series from preserved DuckDB history."""
    from .workbook_sheet_writer import merge_source_sheet

    def specification(con):
        rows = _rows_from_db(con)
        validate_display_rows(rows)
        return {"name": SHEET_NAME, "title": "各国官方劳工输出登记/审批数据",
                "indicators": [item[0] for item in ACTIVE_SERIES.values()],
                "rows": [(row["date"], {name: row.get(series)
                          for series, (name, _) in ACTIVE_SERIES.items()}) for row in rows]}

    # Dictionary rows are inserted in DuckDB before the workbook reads them.
    with db.connect() as con:
        db.upsert_dictionary_rows(con, [
            {"indicator_name": name, "frequency": "月", "unit": "人", "source": source,
             "type": "就业流量", "industry": "劳工", "updated_at": date.today()}
            for name, source in ACTIVE_SERIES.values()
        ])
    return merge_source_sheet(workbook_path.resolve(), specification)
