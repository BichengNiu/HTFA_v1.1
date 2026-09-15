"""从 OPEC MOMR/EIA 抓取阿联酋原油产量与 Brent 油价。

数据链路为：OPEC MOMR + EIA XLS → ``data/UAE/raw/oil/`` → DuckDB 长表 →
``月度_OPEC``/``日度_EIA`` 宽表。Excel 只由 ``merge()`` 重建，不在抓取阶段
直接写入指标数据。
"""

from __future__ import annotations

import calendar
import math
import re
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from . import db
from ._official_download import download_file
from .paths import DATA_DIR
from .workbook_sheet_writer import write_indicator_sheets

RAW_DIR = DATA_DIR / "raw" / "oil"
PRICE_RAW_PATH = RAW_DIR / "brent_spot_daily.xls"
OPEC_RAW_PATH = RAW_DIR / "momr_world_oil_supply.html"
OPEC_HOME_RAW_PATH = RAW_DIR / "momr_home.html"

EIA_BRENT_XLS_URL = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls"
OPEC_MOMR_HOME_URL = "https://publications.opec.org/momr/"
OPEC_PRODUCTION_TABLE = "opec_crude_production_monthly"
EIA_PRICE_TABLE = "eia_brent_spot_daily"

PRODUCTION_SHEET = "月度_OPEC"
PRICE_SHEET = "日度_EIA"
PRODUCTION_INDICATOR = "阿联酋原油产量"
PRICE_INDICATOR = "布伦特现货"
PRODUCTION_SOURCE = "OPEC MOMR（secondary sources）"
PRICE_SOURCE = "U.S. EIA"

@dataclass(frozen=True)
class ProductionObservation:
    """一条 OPEC MOMR 月度原油产量观测，单位为桶/日。"""

    period: date
    production_bpd: float
    source_period: str
    source_file: str = ""


@dataclass(frozen=True)
class PriceObservation:
    """一条 EIA Brent 日度现货价观测，单位为美元/桶。"""

    period: date
    price_usd_bbl: float


def _positive_number(value: object, *, field: str) -> float:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 不是数值：{value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} 不是非负有限数值：{value!r}")
    return number


def discover_opec_supply_url(payload: bytes | str) -> str:
    """从 OPEC MOMR 首页发现当前报告的 World oil supply 页面。"""

    html = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    candidates: list[str] = []
    for anchor in re.finditer(
        r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        body = " ".join(re.sub(r"<[^>]+>", " ", anchor.group("body")).split())
        if body.casefold() != "world oil supply":
            continue
        href = re.search(
            r"\bhref=[\"'](?P<href>/momr/(?:archive/)?chapter/\d+/\d+)[\"']",
            anchor.group("attrs"),
            flags=re.IGNORECASE,
        )
        if href is not None:
            candidates.append(href.group("href"))
    archive_candidate = next(
        (href for href in candidates if "/archive/chapter/" in href),
        None,
    )
    if archive_candidate is not None:
        return urljoin(OPEC_MOMR_HOME_URL, archive_candidate)
    if candidates:
        return urljoin(OPEC_MOMR_HOME_URL, candidates[0])
    raise ValueError("OPEC MOMR 首页未发现当前 World oil supply 页面")


def discover_opec_archive_links(payload: bytes | str) -> list[tuple[date, str]]:
    """发现 OPEC MOMR 首页列出的历史月报，按发布日期倒序返回。"""

    html = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    month_numbers = {
        name: number
        for number, name in enumerate(
            ("january", "february", "march", "april", "may", "june",
             "july", "august", "september", "october", "november", "december"),
            start=1,
        )
    }
    discovered: dict[str, tuple[date, str]] = {}
    for anchor in re.finditer(
        r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        href = re.search(
            r"\bhref=[\"'](?P<href>/momr/archive/(?P<id>\d+)/?)[\"']",
            anchor.group("attrs"),
            flags=re.IGNORECASE,
        )
        if href is None:
            continue
        body = " ".join(re.sub(r"<[^>]+>", " ", anchor.group("body")).split())
        release = re.search(
            r"(?P<month>January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(?P<year>20\d{2})",
            body,
            flags=re.IGNORECASE,
        )
        if release is None:
            continue
        month = month_numbers[release.group("month").casefold()]
        release_date = date(int(release.group("year")), month, 1)
        report_id = href.group("id")
        discovered[report_id] = (
            release_date,
            urljoin(OPEC_MOMR_HOME_URL, href.group("href")),
        )
    return sorted(discovered.values(), reverse=True)


class _OpecTableParser(HTMLParser):
    """Extract rows from one already-isolated HTML table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_opec_latest_production(payload: bytes | str) -> list[ProductionObservation]:
    """Parse UAE monthly observations from OPEC MOMR's secondary-source table.

    Each OPEC report publishes its latest available months in ``tb/d``.
    Historical reports are parsed with the same table and methodology.
    """

    html = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    headings = re.finditer(
        r"<h4\b[^>]*>\s*Table\s+5\s*-\s*\d+\s*</h4>",
        html,
        flags=re.IGNORECASE,
    )
    header: list[str] | None = None
    uae_row: list[str] | None = None
    for heading in headings:
        table_start = html.find("<table", heading.end())
        table_end = html.find("</table>", table_start)
        if table_start < 0 or table_end < 0:
            continue
        parser = _OpecTableParser()
        parser.feed(html[table_start : table_end + len("</table>")])
        candidate_header = next(
            (
                row
                for row in parser.rows
                if row and row[0].casefold() == "secondary sources"
            ),
            None,
        )
        candidate_uae_row = next(
            (row for row in parser.rows if row and row[0].casefold() == "uae"),
            None,
        )
        if candidate_header is not None and candidate_uae_row is not None:
            header = candidate_header
            uae_row = candidate_uae_row
            break
    if header is None or uae_row is None:
        raise ValueError("OPEC MOMR 缺少 Secondary sources/UAE 原油产量表格")

    month_columns: list[tuple[int, date, str]] = []
    for column, value in enumerate(header[1:], start=1):
        match = re.fullmatch(
            r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
            r"(?P<year>\d{2})",
            value,
            flags=re.IGNORECASE,
        )
        if match is None:
            continue
        month = datetime.strptime(match.group("month"), "%b").month
        year = 2000 + int(match.group("year"))
        month_columns.append(
            (column, date(year, month, calendar.monthrange(year, month)[1]), value)
        )

    observations: list[ProductionObservation] = []
    for column, period, source_period in month_columns:
        if column >= len(uae_row):
            continue
        value = uae_row[column].replace("*", "").strip()
        if value in {"", "..", "—", "-"}:
            continue
        observations.append(
            ProductionObservation(
                period=period,
                production_bpd=_positive_number(value, field="OPEC 原油产量") * 1_000,
                source_period=f"{period:%Y-%m}",
            )
        )
    if not observations:
        raise ValueError("OPEC MOMR Secondary sources 表格没有 UAE 月度原油产量")
    return observations


def parse_opec_production_reports(
    paths: list[Path],
) -> list[ProductionObservation]:
    """Parse reports newest-first and keep the newest revision per month."""

    observations: dict[date, ProductionObservation] = {}
    for path in paths:
        for item in parse_opec_latest_production(path.read_bytes()):
            observations.setdefault(
                item.period,
                replace(item, source_file=path.name),
            )
    if not observations:
        raise ValueError("OPEC MOMR 历史月报没有有效的阿联酋原油产量")
    return [observations[key] for key in sorted(observations)]


def _opec_supply_sort_key(path: Path) -> int:
    """Return the numeric archive id so revisions are applied newest-first."""

    match = re.search(r"momr_supply_(\d+)\.html$", path.name)
    return int(match.group(1)) if match else -1


def parse_brent_xls(payload: bytes) -> list[PriceObservation]:
    """Parse the official EIA ``RBRTEd.xls`` daily history workbook."""

    try:
        frame = pd.read_excel(BytesIO(payload), sheet_name="Data 1", header=None)
    except Exception as exc:  # noqa: BLE001 - expose a source-specific error
        raise ValueError("EIA Brent 价格文件无法读取") from exc

    header_rows = [
        row_index
        for row_index in range(frame.shape[0])
        if any(str(value).strip() == "Date" for value in frame.iloc[row_index].tolist())
    ]
    if not header_rows:
        raise ValueError("EIA Brent 价格文件缺少 Date 表头")
    header_row = header_rows[0]
    date_column = next(
        column
        for column, value in enumerate(frame.iloc[header_row].tolist())
        if str(value).strip() == "Date"
    )
    price_column = date_column + 1
    if price_column >= frame.shape[1]:
        raise ValueError("EIA Brent 价格文件缺少价格列")

    observations: dict[date, PriceObservation] = {}
    for row_index in range(header_row + 1, frame.shape[0]):
        raw_date = frame.iat[row_index, date_column]
        raw_price = frame.iat[row_index, price_column]
        if pd.isna(raw_date) and pd.isna(raw_price):
            continue
        parsed_date = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(parsed_date):
            raise ValueError(f"EIA Brent 第 {row_index + 1} 行日期无效：{raw_date!r}")
        if pd.isna(raw_price) or str(raw_price).strip() == "":
            continue
        observation = PriceObservation(
            period=parsed_date.date(),
            price_usd_bbl=_positive_number(raw_price, field="Brent 价格"),
        )
        previous = observations.get(observation.period)
        if previous is not None and previous != observation:
            raise ValueError(f"EIA Brent 存在重复日期：{observation.period}")
        observations[observation.period] = observation

    if not observations:
        raise ValueError("EIA Brent 价格文件没有有效观测")
    return [observations[key] for key in sorted(observations)]


@contextmanager
def _transaction(con):
    con.execute("BEGIN TRANSACTION")
    try:
        yield
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def _dictionary_rows() -> list[dict[str, object]]:
    return [
        {
            "indicator_name": PRODUCTION_INDICATOR,
            "frequency": "月度",
            "unit": "桶/天",
            "source": PRODUCTION_SOURCE,
            "type": "产量",
            "industry": "能源",
            "updated_at": date.today(),
        },
        {
            "indicator_name": PRICE_INDICATOR,
            "frequency": "日度",
            "unit": "美元/桶",
            "source": PRICE_SOURCE,
            "type": "价格",
            "industry": "能源",
            "updated_at": date.today(),
        },
    ]


def _download_inputs(*, force: bool) -> str:
    notes: list[str] = []
    downloads = (
        (EIA_BRENT_XLS_URL, PRICE_RAW_PATH, EIA_BRENT_XLS_URL),
    )
    for url, target, referer in downloads:
        try:
            status = download_file(
                url,
                target,
                force=force,
                min_bytes=256,
                referer=referer,
            )
        except Exception as exc:  # noqa: BLE001 - valid raw cache remains usable
            if not target.is_file() or target.stat().st_size < 256:
                raise
            status = f"缓存（{exc}）"
        notes.append(f"{target.name}:{status}")

    download_file(
        OPEC_MOMR_HOME_URL,
        OPEC_HOME_RAW_PATH,
        # 首页链接会随月报切换，不能按固定文件名长期复用旧首页。
        force=True,
        min_bytes=10_000,
    )
    momr_home = OPEC_HOME_RAW_PATH.read_bytes()
    current_supply_url = discover_opec_supply_url(momr_home)
    current_status = download_file(
        current_supply_url,
        OPEC_RAW_PATH,
        # 当前月报的 World oil supply 页面会随新一期月报切换。
        force=True,
        min_bytes=10_000,
        referer=OPEC_MOMR_HOME_URL,
    )
    notes.append(f"{OPEC_RAW_PATH.name}:{current_status}")

    archive_links = discover_opec_archive_links(momr_home)[:36]
    for release_date, archive_url in archive_links:
        report_id = archive_url.rstrip("/").rsplit("/", 1)[-1]
        archive_path = RAW_DIR / f"momr_archive_{report_id}.html"
        archive_status = download_file(
            archive_url,
            archive_path,
            force=force,
            min_bytes=10_000,
            referer=OPEC_MOMR_HOME_URL,
        )
        archive_supply_url = discover_opec_supply_url(archive_path.read_bytes())
        supply_path = RAW_DIR / f"momr_supply_{report_id}.html"
        supply_status = download_file(
            archive_supply_url,
            supply_path,
            force=force,
            min_bytes=10_000,
            referer=archive_url,
        )
        notes.append(
            f"{release_date:%Y-%m}:{archive_status}/{supply_status}"
        )
    return "；".join(notes)


def update(con, *, force: bool = False, skip_download: bool = False) -> dict[str, object]:
    """抓取并把 OPEC 原油产量、EIA Brent 价格写入 DuckDB。"""

    download_note = "" if skip_download else _download_inputs(force=force)
    opec_paths = [
        OPEC_RAW_PATH,
        *sorted(
            RAW_DIR.glob("momr_supply_*.html"),
            key=_opec_supply_sort_key,
            reverse=True,
        ),
    ]
    production = parse_opec_production_reports(opec_paths)
    prices = parse_brent_xls(PRICE_RAW_PATH.read_bytes())

    production_rows = [
        {
            "period": item.period,
            "production_bpd": item.production_bpd,
            "source_period": item.source_period,
            "source_file": item.source_file or OPEC_RAW_PATH.name,
        }
        for item in production
    ]
    price_rows = [
        {
            "period": item.period,
            "price_usd_bbl": item.price_usd_bbl,
            "source_file": PRICE_RAW_PATH.name,
        }
        for item in prices
    ]
    with _transaction(con):
        db.replace(con, OPEC_PRODUCTION_TABLE, production_rows)
        db.replace(con, EIA_PRICE_TABLE, price_rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"产量 {len(production)} 月（{production[0].source_period} 至 "
        f"{production[-1].source_period}）；Brent 价格 {len(prices)} 日（"
        f"{prices[0].period} 至 {prices[-1].period}）"
    )
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(production) + len(prices), "note": note}


def _metadata(name: str, *, frequency: str, unit: str, source: str) -> dict[str, str]:
    return {
        "frequency": frequency,
        "unit": unit,
        "source": source,
    }


def merge(workbook_path: Path) -> dict[str, object]:
    """从 DuckDB 长表重建 ``月度_OPEC`` 与 ``日度_EIA``。"""

    if not Path(workbook_path).is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    con = db.connect(read_only=True)
    try:
        production_rows = con.execute(
            f"SELECT period, production_bpd FROM {OPEC_PRODUCTION_TABLE} ORDER BY period"
        ).fetchall()
        price_rows = con.execute(
            f"SELECT period, price_usd_bbl FROM {EIA_PRICE_TABLE} ORDER BY period"
        ).fetchall()
    finally:
        con.close()
    if not production_rows or not price_rows:
        raise ValueError("OPEC 原油产量或 Brent 价格长表为空，无法合并")

    counts = write_indicator_sheets(
        Path(workbook_path),
        [
            {
                "name": PRODUCTION_SHEET,
                "title": "阿联酋原油产量（OPEC MOMR）",
                "indicators": [PRODUCTION_INDICATOR],
                "metadata": {
                    PRODUCTION_INDICATOR: _metadata(
                        PRODUCTION_INDICATOR,
                        frequency="月度",
                        unit="桶/天",
                        source=PRODUCTION_SOURCE,
                    )
                },
                "rows": [
                    (period, {PRODUCTION_INDICATOR: value})
                    for period, value in production_rows
                ],
            },
            {
                "name": PRICE_SHEET,
                "title": "Brent 原油现货价（EIA）",
                "indicators": [PRICE_INDICATOR],
                "metadata": {
                    PRICE_INDICATOR: _metadata(
                        PRICE_INDICATOR,
                        frequency="日度",
                        unit="美元/桶",
                        source=PRICE_SOURCE,
                    )
                },
                "rows": [
                    (period, {PRICE_INDICATOR: value})
                    for period, value in price_rows
                ],
            },
        ],
    )
    return {
        "status": "ok",
        "rows": sum(counts.values()),
        "note": (
            f"已重建 {PRODUCTION_SHEET} {counts[PRODUCTION_SHEET]} 行、"
            f"{PRICE_SHEET} {counts[PRICE_SHEET]} 行"
        ),
    }


__all__ = [
    "EIA_BRENT_XLS_URL",
    "EIA_PRICE_TABLE",
    "OPEC_MOMR_HOME_URL",
    "OPEC_HOME_RAW_PATH",
    "OPEC_PRODUCTION_TABLE",
    "OPEC_RAW_PATH",
    "PRICE_INDICATOR",
    "PRICE_RAW_PATH",
    "PRICE_SHEET",
    "PRODUCTION_INDICATOR",
    "PRODUCTION_SHEET",
    "PriceObservation",
    "ProductionObservation",
    "merge",
    "parse_brent_xls",
    "parse_opec_latest_production",
    "parse_opec_production_reports",
    "discover_opec_archive_links",
    "discover_opec_supply_url",
    "update",
]
