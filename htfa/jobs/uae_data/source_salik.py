"""Salik（迪拜收费公路运营商）「Registered Active Vehicles」季度入库。

数据来源：Salik Company PJSC 投资者关系（https://www.salik.ae/Investors）季度财报 /
投资者演示 PDF 中的官方 KPI「Registered active vehicles (mn)」。Salik 只按季度披露该
绝对数（无月度序列）。

- 原始件：`data/UAE/raw/salik/*.pdf`（由投资者关系页自动发现和下载）。
- 编译序列：`data/UAE/raw/salik/registered_active_vehicles_quarterly.csv`
  （period_end, vehicles_mn, source, note；各数值注明出处文件，横图读数可能取整）。
- 入库表：`salik_active_vehicles_quarterly`（period 季末日, value 百万辆, source, note）。

本模块只负责把官方 PDF 提取后写入 DuckDB；Excel 的「季度_Salik」由
``merge()`` 统一重建，避免来源模块绕过 DuckDB 直接写表。

单位：百万辆（mn）。
"""

from __future__ import annotations

import csv
import os
import re
import tempfile
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from pypdf import PdfReader

from .paths import DATA_DIR

from .workbook_sheet_writer import merge_source_sheet


from . import db  # noqa: E402
from ._official_download import download_file, fetch_bytes  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TARGET_SHEET = "季度_Salik"
RAW_CSV = DATA_DIR / "raw" / "salik" / "registered_active_vehicles_quarterly.csv"
RAW_DIR = DATA_DIR / "raw" / "salik"
SALIK_RESULTS_URL = "https://www.salik.ae/en/investors/results-and-reports?download=1"
TABLE = "salik_active_vehicles_quarterly"
SOURCE_NAME = "Salik (salik.ae IR)"
UNIT = "百万辆"
FREQUENCY = "季"
INDUSTRY = "交通"
INDICATOR_NAME = "阿联酋:Salik注册活跃车辆:季末值"

_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    period DATE           NOT NULL PRIMARY KEY,
    value  DECIMAL(28, 3),
    source VARCHAR,
    note   VARCHAR
)
"""

_PDF_LINK_RE = re.compile(
    r"\bhref=[\"'](?P<href>[^\"']+\.pdf(?:\?[^\"']*)?)[\"']",
    re.I,
)
_PERIOD_RE = re.compile(
    r"(?:(?:q|quarter)[_-]?(?P<q>[1-4])|(?P<h>h[12])|(?P<nine>9m)|(?P<fy>fy))[\W_]*(?P<year>20\d{2})",
    re.I,
)
_ACTIVE_VEHICLES_RE = re.compile(
    r"registered\s+active\s+vehicles.{0,500}?"
    r"(?:as\s+of|as\s+at).{0,160}?"
    r"(?:c\.?\s*)?(?P<value>\d+(?:\.\d+)?)\s*mn",
    re.I,
)


def _period_from_filename(name: str) -> date | None:
    match = _PERIOD_RE.search(name)
    if match is None:
        return None
    year = int(match.group("year"))
    quarter = (int(match.group("h")[1]) * 2 if match.group("h")
               else 3 if match.group("nine")
               else 4 if match.group("fy") else int(match.group("q")))
    month = quarter * 3
    return date(year, month, monthrange(year, month)[1])


def _discover_official_pdfs() -> list[tuple[date, str, Path]]:
    """Find Salik investor presentations from the official IR page."""

    html = fetch_bytes(SALIK_RESULTS_URL, referer="https://www.salik.ae/", browser_transport=True).decode(
        "utf-8"
    )
    found: dict[str, tuple[date, str, Path]] = {}
    for match in _PDF_LINK_RE.finditer(html):
        href = match.group("href").replace("&amp;", "&")
        url = urljoin(SALIK_RESULTS_URL, href)
        parsed = urlparse(url)
        filename = unquote(Path(parsed.path).name)
        lower = filename.casefold()
        if not any(folder in parsed.path.casefold() for folder in ("financial-statements", "other-reports")):
            continue
        if not any(word in lower for word in ("presentation", "investor")):
            continue
        period = _period_from_filename(filename)
        if period is None:
            if not re.search(r"(?:q[1-4]|h[12]|9m|fy)[\W_]", lower):
                # General corporate decks dated by publication month do not
                # identify a financial reporting quarter.
                continue
            raise ValueError(f"Salik investor PDF filename has no reporting period: {filename}")
        found[url] = (period, url, RAW_DIR / filename)
    if not found:
        raise ValueError("Salik investor relations page contains no recognized presentation PDFs")
    return sorted(found.values(), key=lambda item: item[0])


def _download_presentations(*, force: bool) -> tuple[int, int]:
    downloaded = 0
    existing = 0
    for period, url, target in _discover_official_pdfs():
        # Backfill missing quarters too; presentations often contain the
        # absolute vehicle KPI while earnings slides contain only YoY growth.
        status = download_file(
            url,
            target,
            force=force,
            min_bytes=1024,
            referer=SALIK_RESULTS_URL,
            browser_transport=True,
        )
        if status == "downloaded":
            downloaded += 1
        else:
            existing += 1
    return downloaded, existing


def _extract_absolute_value(path: Path) -> float | None:
    """Extract an absolute ``mn`` KPI, never infer it from a YoY percentage."""

    reader = PdfReader(str(path))
    text = " ".join((page.extract_text() or "") for page in reader.pages)
    text = re.sub(r"\s+", " ", text)
    match = _ACTIVE_VEHICLES_RE.search(text)
    if match:
        return float(match.group("value"))
    return None


def _refresh_csv_from_pdfs() -> int:
    """Merge newly extracted official values into the cached compilation CSV."""

    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"Salik 编译序列缺失: {RAW_CSV}")
    with RAW_CSV.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    by_period = {
        record.get("period_end", "").strip(): record
        for record in records
        if record.get("period_end", "").strip()
    }
    added = 0
    for path in sorted(RAW_DIR.glob("*.pdf")):
        period = _period_from_filename(path.name)
        if period is None:
            raise ValueError(f"Salik PDF filename has no reporting period: {path.name}")
        value = _extract_absolute_value(path)
        if value is None:
            continue
        key = period.isoformat()
        record = by_period.get(key)
        if record is not None and (record.get("vehicles_mn") or "").strip():
            continue
        if record is None:
            record = {
                "period_end": key,
                "vehicles_mn": "",
                "source": "",
                "note": "",
            }
            by_period[key] = record
            added += 1
        record["vehicles_mn"] = f"{value:g}"
        record["source"] = path.name
        record["note"] = "官方投资者演示自动提取：Registered active vehicles (mn)"

    ordered = [by_period[key] for key in sorted(by_period)]
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{RAW_CSV.name}.", suffix=".part", dir=RAW_CSV.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["period_end", "vehicles_mn", "source", "note"]
            )
            writer.writeheader()
            writer.writerows(ordered)
        os.replace(temporary_name, RAW_CSV)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return added


# ---------------------------------------------------------------------------
# 解析 / 入库
# ---------------------------------------------------------------------------


def _read_rows() -> list[dict]:
    """读编译 CSV；vehicles_mn 为空（如某期未给绝对数）则跳过该行。"""
    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"Salik 编译序列缺失: {RAW_CSV}")
    rows: list[dict] = []
    with RAW_CSV.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            period_end = record.get("period_end", "").strip()
            value_text = (record.get("vehicles_mn") or "").strip()
            if not period_end:
                if value_text:
                    raise ValueError("Salik CSV row has a value but no period_end")
                continue
            try:
                period = date.fromisoformat(period_end)
            except ValueError as exc:
                raise ValueError(
                    f"Salik CSV row has invalid period_end: {period_end!r}"
                ) from exc
            if not value_text:
                continue
            try:
                value = float(value_text)
            except ValueError as exc:
                raise ValueError(
                    f"Salik CSV row has invalid vehicles_mn: {value_text!r}"
                ) from exc
            rows.append(
                {
                    "period": period,
                    "value": value,
                    "source": record.get("source", "").strip(),
                    "note": record.get("note", "").strip(),
                }
            )
    rows.sort(key=lambda r: r["period"])
    return rows


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """自动发现/下载 Salik 投资者演示，刷新 CSV 后整表写入 DuckDB。"""

    download_note = ""
    if not skip_download:
        # Refresh the latest discovered presentation even when its URL is
        # unchanged; investor decks may be corrected after publication.
        downloaded, existing = _download_presentations(force=True)
        download_note = f"官网缓存：新增 {downloaded}，复用 {existing}"

    extracted = _refresh_csv_from_pdfs()
    rows = _read_rows()
    if not rows:
        raise ValueError("salik_active_vehicles_quarterly 输入为空，拒绝入库")

    with db.transaction(con):
        db.ensure(con, TABLE, _TABLE_DDL)
        db.replace(con, TABLE, rows)
        db.upsert_dictionary_rows(
            con,
            [
                {
                    "indicator_name": INDICATOR_NAME,
                    "frequency": FREQUENCY,
                    "unit": UNIT,
                    "source": SOURCE_NAME,
                    "type": "存量",
                    "industry": INDUSTRY,
                    "updated_at": date.today(),
                }
            ],
        )

    periods = [row["period"].isoformat() for row in rows]
    note = (
        f"{len(rows)} 个季末观测（{periods[0]} 至 {periods[-1]}），"
        "由 merge() 从 DuckDB 写入 Excel"
    )
    if extracted:
        note += f"；PDF 自动补入 {extracted} 期"
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(rows), "note": note}


def _sheet_spec(con) -> dict[str, Any]:
    indicator = INDICATOR_NAME
    rows = [(period, {indicator: value}) for period, value in con.execute(
        "SELECT period, value FROM salik_active_vehicles_quarterly ORDER BY period"
    ).fetchall()]
    return {
        "name": TARGET_SHEET,
        "title": "Salik 注册活跃车辆季度指标",
        "indicators": [indicator],
        "rows": rows,
    }


def merge(workbook_path: Path) -> dict:
    """Rebuild this source's workbook sheet from DuckDB."""
    return merge_source_sheet(workbook_path, _sheet_spec)
