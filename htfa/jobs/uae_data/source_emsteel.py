"""Emsteel public monthly rebar quotations, including explicitly flagged backfills.

Quanto supplies the published history; month-specific public articles fill gaps.
This is a nominal quotation compilation, not a transaction-price index. Source
averages, inferred bases, FX conversions and rebate changes remain traceable.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from calendar import monthrange
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.comments import Comment

from . import db
from ._official_download import write_json_atomic
from .paths import DATA_DIR
from .workbook_sheet_writer import read_indicator_metadata, write_indicator_sheets

RAW_DIR = DATA_DIR / "raw" / "emsteel"
QUANTO_URL = "https://quantohq.com/assets/data/price-index.json"
TARGET_SHEET = "月度_EMSTEEL"
INDICATOR = "阿联酋:Emsteel钢筋月度公开报价:EXW:汇编含推算"
SOURCE = "Quanto / SteelOrbis / SEAISI / AISU（公开报价汇编，含推算）"
START = "2024-01"
MIN_END = "2026-10"
SO = "https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/"
APR24 = SO + "uae-based-esakeeps-rebar-prices-unchanged-amid-stable-demand-1332947.htm"
FEB24 = "https://www.seaisi.org/details/24179?type=news-rooms"

# Parsing recipes, not hand-maintained prices. Guards bind each recipe to the
# production/delivery month, rather than the article's publication month.
GAP_RULES = {
    "2024-01": (FEB24, "February-delivery", "difference"),
    "2024-02": (FEB24, "February-delivery", "direct"),
    "2024-03": (APR24, "offers for March have been kept stable for April", "rollover"),
    "2024-05": (SO + "uaes-esa-issues-stable-rebar-price-for-may-amid-higher-stocks-1337404.htm", "for May output", "basis_inferred"),
    "2024-06": (SO + "uae-based-esa-cuts-rebar-prices-for-june-output-1341503.htm", "for June production", "direct"),
    "2024-07": ("https://aisusteel.org/en/news/emirates-steel-arkan-keeps-rebar-prices-unchanged-for-july-output/2256", "July production", "aisu"),
    "2024-09": ("https://www.seaisi.org/details/25300?type=news-rooms", "for September deliveries", "direct"),
    "2025-02": (SO + "uae-rebar-suppliers-keep-offers-for-february-stable-in-line-with-emsteel-1376679.htm", "for February production remained stable", "direct"),
    "2025-04": (SO + "uaes-emsteelcontinues-to-keep-rebar-offers-unchanged-for-the-third-consecutive-month-in-april-1384295.htm", "for April production", "fx"),
    "2025-05": (SO + "uae-based-emsteelissues-rebar-prices-for-may-amid-stable-demand-1388335.htm", "offers for May production", "direct"),
    "2025-06": (SO + "uaes-emsteel-keeps-rebar-prices-stable-for-june-amid-lively-domestic-trade-1393041.htm", "for June production is unchanged", "direct"),
}

DDL = """CREATE TABLE IF NOT EXISTS emsteel_monthly (
    period DATE NOT NULL,
    indicator VARCHAR NOT NULL,
    value DECIMAL(18, 3) NOT NULL,
    quality_flag VARCHAR NOT NULL,
    original_value DECIMAL(18, 3) NOT NULL,
    original_currency VARCHAR NOT NULL,
    fx_rate DECIMAL(12, 6),
    source_url VARCHAR NOT NULL,
    source_title VARCHAR,
    evidence_urls VARCHAR,
    source_file VARCHAR NOT NULL,
    source_sha256 VARCHAR NOT NULL,
    note VARCHAR,
    PRIMARY KEY (period, indicator)
)"""


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def page_text(raw: str) -> str:
    parser = _PageText()
    parser.feed(raw)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _match(pattern: str, text: str) -> Decimal:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        raise ValueError(f"Emsteel article changed or price is unavailable: {pattern}")
    return Decimal(match.group(1).replace(",", ""))


def parse_gap(period: str, text: str) -> dict:
    """Extract one gap from its guarded article; never interpolate missing prices."""
    url, guard, method = GAP_RULES[period]
    if guard.casefold() not in text.casefold():
        raise ValueError(f"Emsteel article period guard failed: {period}")
    currency, fx = "AED", None
    if method == "fx":
        original = _match(r"\$([\d,.]+)/mt ex-works,? for April production", text)
        fx = _match(r"\$1\s*=\s*AED\s*([\d.]+)", text)
        value = original * fx
        flag = "fx_converted"
    elif method in {"direct", "difference", "rollover"}:
        original = _match(
            r"AED\s*([\d,.]+)/(?:mt|tonne|t)\)?\s*(?:\(\$[\d,.]+\)\s*)?ex-works",
            text,
        )
        value, flag = original, "reported"
        if method == "difference":
            increase = _match(r"up AED\s*([\d,.]+)/tonne on January", text)
            value = original - increase
            flag = "difference_derived"
        elif method == "rollover":
            flag = "rollover_derived"
    elif method == "aisu":
        original = _match(r"AED\s*([\d,.]+)\s*\(USD\s*[\d,.]+\) per ton EXW", text)
        value, flag = original, "reported"
    else:
        original = _match(r"\(AED\s*([\d,.]+)/mt\) for May output", text)
        value, flag = original, "basis_inferred"
    if method == "fx":
        currency = "USD"
    notes = {
        "difference": "1月=2月报价减报道明确给出的涨幅；original_value记录2月基数。",
        "rollover": "4月报道明确称与3月持平，按不变价回溯；非插值。",
        "basis_inferred": "原文基础报价未直接标EXW，另列CPT价格；EXW口径为推断。",
        "fx": "按同文USD/AED汇率折算，保留原币报价，不与近似AED值混写。",
    }
    note = notes.get(method, "当期生产/交货月份钢厂报价；不是月内成交均价。")
    if period == "2025-02":
        note += "另有回顾报道概括2—6月约675美元；保留当期明确官方报价722美元，不平均冲突值。"
    if period == "2025-05":
        note += "原文将与此前722美元报价的差额联系到常客优惠调整，并称实际成交水平基本未变。"
    return dict(value=value, quality_flag=flag, original_value=original,
                original_currency=currency, fx_rate=fx, source_url=url,
                source_title=f"Emsteel {period} public quotation ({method})",
                evidence_urls=json.dumps([url]), note=note)


def expected_periods(end: str) -> list[str]:
    return [f"{y}-{m:02d}" for y in range(2024, 2027) for m in range(1, 13)
            if START <= f"{y}-{m:02d}" <= end]


def build_rows(payload: dict, article_loader, *, today: date | None = None) -> list[dict]:
    """Validate the catalogue, provenance, closed months and continuous coverage."""
    today = today or date.today()
    items = [x for x in payload["items"] if x.get("id") == "emsteel-xw"]
    if len(items) != 1 or any(items[0].get(k) != v for k, v in {
        "frequency": "monthly", "currency": "AED", "vat": "excluded",
        "unit_en": "tonne", "basis_en": "Monthly mill list price",
    }.items()) or "ex-works" not in items[0].get("spec_en", ""):
        raise ValueError("Quanto Emsteel catalogue/basis changed")
    observations = {}
    for item in payload["observations"]:
        period = item.get("period", "")
        if item.get("item_id") != "emsteel-xw" or item.get("status") != "published":
            continue
        if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", period):
            raise ValueError(f"Invalid Emsteel period: {period}")
        if START <= period <= "2026-12" and period < today.strftime("%Y-%m"):
            if period in observations:
                raise ValueError(f"Duplicate published Emsteel month: {period}")
            observations[period] = item
    if not observations or max(observations) < MIN_END:
        raise ValueError(f"Emsteel history regressed; need through {MIN_END}")
    rows = []
    for period in expected_periods(max(observations)):
        if period in observations:
            item = observations[period]
            note = item.get("note", "")
            flag = "compiled_reported"
            if "Mean of sources" in note:
                flag = "compiled_source_mean"
            elif "carried" in note.lower() or item.get("source_title", "").startswith("unchanged per"):
                flag = "compiled_rollover"
            if "year inferred" in item.get("source_title", ""):
                flag += ";year_inferred"
            value = item.get("price")
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError(f"Invalid Emsteel price: {period}")
            row = dict(value=value, quality_flag=flag, original_value=value,
                       original_currency="AED", fx_rate=None,
                       source_url=QUANTO_URL, source_title=item["source_title"],
                       evidence_urls=json.dumps([item["source_url"], *item.get("extra_source_urls", [])]),
                       source_file="quanto.json", note=note)
            if period == "2025-12":
                row["note"] += "；AISU次年1月不变价2648与本条2644存在冲突，未取平均。"
        elif period in GAP_RULES:
            url = GAP_RULES[period][0]
            raw, filename = article_loader(url)
            row = parse_gap(period, page_text(raw.decode("utf-8")))
            row["source_file"] = filename
            row["source_sha256"] = hashlib.sha256(raw).hexdigest()
        else:
            raise ValueError(f"No verified Emsteel price for {period}; refusing to forward-fill")
        if not math.isfinite(float(row["value"])) or not 0 < float(row["value"]) < 20000:
            raise ValueError(f"Out-of-range Emsteel price: {period}")
        if not row["source_url"].startswith("https://"):
            raise ValueError(f"Missing Emsteel provenance: {period}")
        year, month = map(int, period.split("-"))
        row.update(period=date(year, month, monthrange(year, month)[1]), indicator=INDICATOR)
        rows.append(row)
    return rows


def _cached(url: str, *, skip_download: bool) -> tuple[bytes, str]:
    filename = "quanto.json" if url == QUANTO_URL else hashlib.sha256(url.encode()).hexdigest()[:20] + ".html"
    path = RAW_DIR / filename
    if not skip_download:
        from curl_cffi import requests

        response = requests.get(url, impersonate="chrome", timeout=45)
        response.raise_for_status()
        raw = response.content
        if not raw:
            raise ValueError(f"Empty Emsteel response: {url}")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)
    return path.read_bytes(), filename


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Download public evidence, validate every month, then atomically replace DB rows."""
    raw, _ = _cached(QUANTO_URL, skip_download=skip_download)
    cache = {}

    def loader(url):
        if url not in cache:
            cache[url] = _cached(url, skip_download=skip_download)
        return cache[url]

    rows = build_rows(json.loads(raw), loader)
    for row in rows:
        row.setdefault("source_sha256", hashlib.sha256(raw).hexdigest())
    # Reject loss of a newer previously accepted month before replacing history.
    db.ensure(con, "emsteel_monthly", DDL)
    old_latest = con.execute("SELECT max(period) FROM emsteel_monthly").fetchone()[0]
    if old_latest and old_latest > rows[-1]["period"]:
        raise ValueError("Emsteel update would truncate accepted history")
    with db.transaction(con):
        db.replace(con, "emsteel_monthly", rows)
        db.upsert_dictionary_rows(con, [dict(
            indicator_name=INDICATOR, frequency="月", unit="迪拉姆/吨",
            source=SOURCE, type="价格", industry="钢铁", updated_at=date.today(),
        )])
    write_json_atomic(RAW_DIR / "quality_report.json", {
        "months": len(rows), "first": str(rows[0]["period"]),
        "latest": str(rows[-1]["period"]), "missing": [],
        "flags": {str(r["period"]): r["quality_flag"] for r in rows},
        "limitation": "名义公开报价汇编，含推算、折算、来源均值；非同规格成交均价。",
    })
    return {"status": "ok", "rows": len(rows),
            "note": f"{rows[0]['period']} 至 {rows[-1]['period']} 连续报价；保留质量标记"}


def merge(workbook_path: Path) -> dict:
    """Read values AND provenance from DuckDB; atomically publish a commented sheet."""
    from .uae_metadata import sync_workbook_dictionary

    path = Path(workbook_path).resolve()
    if path.with_name(f"~${path.name}").exists():
        raise PermissionError("请先关闭 Excel 工作簿")
    with db.connect(read_only=True) as con:
        records = con.execute(
            "SELECT period, value, quality_flag, source_url, evidence_urls, note "
            "FROM emsteel_monthly ORDER BY period"
        ).fetchall()
        metadata = read_indicator_metadata(con, [INDICATOR])
    if not records:
        raise ValueError("emsteel_monthly is empty")
    backups = path.parent / "backups"
    backups.mkdir(exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".emsteel-", suffix=".tmp.xlsx", dir=path.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        shutil.copy2(path, temporary)
        write_indicator_sheets(temporary, [dict(
            name=TARGET_SHEET, title="Emsteel钢筋月度公开报价（汇编含推算，非成交均价）",
            indicators=[INDICATOR], metadata=metadata,
            rows=[(r[0], {INDICATOR: r[1]}) for r in records],
        )])
        workbook = load_workbook(temporary)
        try:
            sheet = workbook[TARGET_SHEET]
            for index, record in enumerate(reversed(records), 7):
                _, _, flag, url, evidence, note = record
                sheet.cell(index, 2).number_format = "0.000"
                sheet.cell(index, 2).comment = Comment(
                    f"质量标记：{flag}\n数据来源：{url}\n原始报道：{evidence}\n说明：{note or ''}",
                    "HTFA 数据来源",
                )
            workbook.save(temporary)
        finally:
            workbook.close()
        sync_workbook_dictionary(temporary)
        check = load_workbook(temporary, read_only=True, data_only=True)
        try:
            actual = [(r[0].date(), Decimal(str(r[1]))) for r in
                      check[TARGET_SHEET].iter_rows(min_row=7, max_col=2, values_only=True)]
            if actual != [(r[0], r[1]) for r in reversed(records)]:
                raise ValueError("Emsteel workbook/DB round-trip mismatch")
        finally:
            check.close()
        from datetime import datetime

        shutil.copy2(path, backups / f"emsteel_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "ok", "rows": len(records), "note": f"{TARGET_SHEET} 已从库同步，含逐月来源批注"}
