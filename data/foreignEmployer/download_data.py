"""Download official labour-outflow data used for the UAE proxy.

The downloader deliberately keeps raw files local.  The repository .gitignore
excludes data artifacts while retaining this script and the methodology README.
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"

DMW_CMS_URL = "https://wcms.dmw.gov.ph/api/compendium-releases"
DMW_ARCHIVE_ROOT = (
    "https://dmw.gov.ph/archives/v1/resources/dsms/DMW/Externals/2025/"
    "Statistics"
)
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
                time.sleep(2 ** attempt)
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


def dmw_static_2025_urls() -> list[dict[str, Any]]:
    months = [
        (1, "JAN", "2024 Jan 2025"),
        (2, "FEB", "2024 Feb 2025"),
        (3, "MAR", "2024 Mar 2025"),
        (4, "APR", "2024 Apr 2025"),
        (5, "MAY", "2024 May 2025"),
        (6, "JUNE", "2024 June 2025"),
        (7, "JULY", "2024 July 2025"),
        (8, "AUGUST", "2024 August 2025"),
        (9, "SEPTEMBER", "2024 September 2025"),
        (10, "OCTOBER", "2024 October 2025"),
    ]
    records: list[dict[str, Any]] = []
    for month, folder, label in months:
        filename = f"TAB 11 - Landbased Deployment by Destination ({label}).xlsx"
        records.append(
            {
                "year": 2025,
                "month": month,
                "url": f"{DMW_ARCHIVE_ROOT}/{folder}/{filename}",
                "source": "DMW archive",
            }
        )
    filename = (
        "TAB 11 - Landbased Deployment by Destination "
        "(2024-November 2025).xlsx"
    )
    records.append(
        {
            "year": 2025,
            "month": 11,
            "url": (
                "https://dmw.gov.ph/archives/v1/resources/dsms/DMW/"
                f"Externals/2025/Statistics/NOVEMBER/{filename}"
            ),
            "source": "DMW archive",
        }
    )
    return records


def dmw_cms_urls(session: requests.Session) -> list[dict[str, Any]]:
    params = {
        "filters[release_type][$eq]": "monthly",
        "populate[reports][populate][files][populate][0]": "file",
        "sort[0]": "year:asc",
        "sort[1]": "month:asc",
        "pagination[pageSize]": 100,
    }
    response = session.get(DMW_CMS_URL, params=params, timeout=90)
    response.raise_for_status()
    records: list[dict[str, Any]] = []
    for release in response.json().get("data", []):
        report = next(
            (
                item
                for item in release.get("reports", [])
                if str(item.get("tab_number")) == "11"
            ),
            None,
        )
        if report is None:
            continue
        file_record = next(
            (
                item
                for item in report.get("files", [])
                if item.get("file_type") == "excel"
            ),
            None,
        )
        if not file_record:
            continue
        file_url = (file_record.get("file") or {}).get("url")
        if not file_url:
            continue
        records.append(
            {
                "year": int(release["year"]),
                "month": int(release["month"]),
                "url": file_url,
                "published_at": release.get("publishedAt"),
                "source": "DMW CMS",
            }
        )
    return records


def download_philippines(
    session: requests.Session, refresh: bool
) -> list[dict[str, Any]]:
    directory = RAW_DIR / "philippines"
    records = dmw_static_2025_urls() + dmw_cms_urls(session)
    unique = {
        (record["year"], record["month"]): record for record in records
    }
    results = []
    for (_year, _month), record in sorted(unique.items()):
        destination = directory / (
            f"philippines_dmw_{record['year']}_{record['month']:02d}.xlsx"
        )
        save_download(session, record["url"], destination, b"PK", refresh)
        results.append({**record, "path": str(destination.relative_to(BASE_DIR))})
    return results


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def discover_nepal_reports(session: requests.Session) -> list[dict[str, Any]]:
    reports: dict[tuple[int, int], dict[str, Any]] = {}
    for page in range(1, 8):
        response = session.get(
            DOFE_MONTHLY_URL, params={"page": page}, timeout=90
        )
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
                continue
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
        results.append({**record, "path": str(destination.relative_to(BASE_DIR))})
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
                BMET_OEP_URL,
                params=params,
                headers=headers,
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            if "payload" not in payload:
                raise RuntimeError(f"Unexpected OEP response for {year}-{month:02d}")
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
                "path": str(destination.relative_to(BASE_DIR)),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload files that already exist.",
    )
    parser.add_argument(
        "--source",
        choices=("all", "philippines", "nepal", "bangladesh"),
        default="all",
    )
    args = parser.parse_args()

    session = build_session()
    manifest: dict[str, Any] = {
        "downloaded_on": date.today().isoformat(),
        "sources": {},
    }
    if args.source != "all" and MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["sources"].update(existing.get("sources", {}))
    if args.source in ("all", "philippines"):
        manifest["sources"]["philippines"] = download_philippines(
            session, args.refresh
        )
    if args.source in ("all", "nepal"):
        manifest["sources"]["nepal"] = download_nepal(session, args.refresh)
    if args.source in ("all", "bangladesh"):
        manifest["sources"]["bangladesh"] = download_bangladesh(
            session, args.refresh
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for source, records in manifest["sources"].items():
        print(f"{source}: {len(records)} observations/files")
    print(f"Manifest: {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
