"""从美国能源信息署（EIA）抓取阿联酋原油产量与 Brent 油价。

数据链路为：EIA API/XLS → ``data/UAE/raw/eia_oil/`` → DuckDB 长表 →
``月度_EIA``/``日度_EIA`` 宽表。Excel 只由 ``merge()`` 重建，不在抓取阶段
直接写入指标数据。
"""

from __future__ import annotations

import calendar
import json
import math
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from . import db
from ._official_download import download_file
from .paths import DATA_DIR
from .workbook_sheet_writer import write_indicator_sheets

RAW_DIR = DATA_DIR / "raw" / "eia_oil"
PRODUCTION_RAW_PATH = RAW_DIR / "uae_crude_production.json"
PRICE_RAW_PATH = RAW_DIR / "brent_spot_daily.xls"

EIA_API_URL = "https://api.eia.gov/v2/international/data/"
EIA_PRODUCTION_PAGE = (
    "https://www.eia.gov/international/data/world/crude-oil-production.php"
    "?country=UAE&dl=none"
)
EIA_BRENT_XLS_URL = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls"
EIA_DEFAULT_API_KEY = "DEMO_KEY"
EIA_PRODUCTION_TABLE = "eia_crude_production_monthly"
EIA_PRICE_TABLE = "eia_brent_spot_daily"

PRODUCTION_SHEET = "月度_EIA"
PRICE_SHEET = "日度_EIA"
PRODUCTION_INDICATOR = "阿联酋原油产量"
PRICE_INDICATOR = "布伦特现货"
PRODUCTION_SOURCE = "U.S. EIA International"
PRICE_SOURCE = "U.S. EIA"

_PERIOD_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")


@dataclass(frozen=True)
class ProductionObservation:
    """一条 EIA 月度原油产量观测，单位为桶/日。"""

    period: date
    production_bpd: float
    source_period: str


@dataclass(frozen=True)
class PriceObservation:
    """一条 EIA Brent 日度现货价观测，单位为美元/桶。"""

    period: date
    price_usd_bbl: float


def _api_key() -> str:
    return os.environ.get("EIA_API_KEY", EIA_DEFAULT_API_KEY).strip() or EIA_DEFAULT_API_KEY


def production_url() -> str:
    """Return the public EIA API URL for UAE crude production."""

    query = [
        ("api_key", _api_key()),
        ("frequency", "monthly"),
        ("data[]", "value"),
        ("facets[countryRegionId][]", "ARE"),
        ("facets[productId][]", "57"),
        ("facets[activityId][]", "1"),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        ("length", "5000"),
    ]
    return f"{EIA_API_URL}?{urlencode(query)}"


def _parse_period(value: object) -> tuple[date, str]:
    text = str(value or "").strip()
    match = _PERIOD_RE.fullmatch(text)
    if match is None:
        raise ValueError(f"EIA period 不是 YYYY-MM：{value!r}")
    year = int(match.group("year"))
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise ValueError(f"EIA period 月份无效：{value!r}")
    return date(year, month, calendar.monthrange(year, month)[1]), text


def _positive_number(value: object, *, field: str) -> float:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"EIA {field} 不是数值：{value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"EIA {field} 不是非负有限数值：{value!r}")
    return number


def parse_production_payload(payload: bytes | str) -> list[ProductionObservation]:
    """Parse EIA API JSON and convert thousand barrels/day to barrels/day."""

    try:
        document = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("EIA 原油产量响应不是有效 JSON") from exc

    records = document.get("response", {}).get("data")
    if not isinstance(records, list):
        raise ValueError("EIA 原油产量响应缺少 response.data")

    observations: dict[date, ProductionObservation] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("countryRegionId")) != "ARE":
            continue
        if str(record.get("productId")) != "57":
            continue
        if str(record.get("activityId")) != "1":
            continue
        unit = str(record.get("unit") or "").upper()
        unit_name = str(record.get("unitName") or "").casefold()
        if unit != "TBPD" and "thousand barrels per day" not in unit_name:
            raise ValueError(f"EIA 原油产量单位异常：{record.get('unitName')!r}")

        period, source_period = _parse_period(record.get("period"))
        observation = ProductionObservation(
            period=period,
            production_bpd=_positive_number(
                record.get("value"), field="原油产量"
            )
            * 1_000,
            source_period=source_period,
        )
        previous = observations.get(period)
        if previous is not None and previous != observation:
            raise ValueError(f"EIA 原油产量存在重复月份：{source_period}")
        observations[period] = observation

    if not observations:
        raise ValueError("EIA 原油产量响应没有阿联酋 productId=57 的有效观测")
    return [observations[key] for key in sorted(observations)]


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
        (production_url(), PRODUCTION_RAW_PATH, EIA_PRODUCTION_PAGE),
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
    return "；".join(notes)


def update(con, *, force: bool = False, skip_download: bool = False) -> dict[str, object]:
    """抓取并把 EIA 原油产量、Brent 价格写入 DuckDB。"""

    download_note = "" if skip_download else _download_inputs(force=force)
    production = parse_production_payload(PRODUCTION_RAW_PATH.read_bytes())
    prices = parse_brent_xls(PRICE_RAW_PATH.read_bytes())

    production_rows = [
        {
            "period": item.period,
            "production_bpd": item.production_bpd,
            "source_period": item.source_period,
            "source_file": PRODUCTION_RAW_PATH.name,
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
        db.replace(con, EIA_PRODUCTION_TABLE, production_rows)
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
    """从 EIA DuckDB 长表重建 ``月度_EIA`` 与 ``日度_EIA``。"""

    if not Path(workbook_path).is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    con = db.connect(read_only=True)
    try:
        production_rows = con.execute(
            f"SELECT period, production_bpd FROM {EIA_PRODUCTION_TABLE} ORDER BY period"
        ).fetchall()
        price_rows = con.execute(
            f"SELECT period, price_usd_bbl FROM {EIA_PRICE_TABLE} ORDER BY period"
        ).fetchall()
    finally:
        con.close()
    if not production_rows or not price_rows:
        raise ValueError("EIA 原油产量或 Brent 价格长表为空，无法合并")

    counts = write_indicator_sheets(
        Path(workbook_path),
        [
            {
                "name": PRODUCTION_SHEET,
                "title": "阿联酋原油产量（EIA）",
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
    "EIA_API_URL",
    "EIA_BRENT_XLS_URL",
    "EIA_PRODUCTION_PAGE",
    "EIA_PRODUCTION_TABLE",
    "EIA_PRICE_TABLE",
    "PRICE_INDICATOR",
    "PRICE_RAW_PATH",
    "PRICE_SHEET",
    "PRODUCTION_INDICATOR",
    "PRODUCTION_RAW_PATH",
    "PRODUCTION_SHEET",
    "PriceObservation",
    "ProductionObservation",
    "merge",
    "parse_brent_xls",
    "parse_production_payload",
    "production_url",
    "update",
]
