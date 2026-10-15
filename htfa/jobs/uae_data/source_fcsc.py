"""Federal Competitiveness and Statistics Centre monthly CPI inflation rates.

Fetches national all-items and food-and-beverages CPI series, prefers FCSC's
published annual-change measure, fills its 2022 gap from index levels, and
stores the resulting monthly YoY report series in DuckDB.
"""

from __future__ import annotations

import csv
import io
from calendar import monthrange
from datetime import date, datetime
from math import isfinite
from pathlib import Path

from . import db
from ._official_download import download_file
from .paths import DATA_DIR
from .workbook_sheet_writer import merge_source_sheet


RAW_DIR = DATA_DIR / "raw" / "fcsc"
RAW_CSV = RAW_DIR / "df_cpi_3.2.0.csv"
TARGET_SHEET = "月度_FCSC"
SOURCE_NAME = "FCSC UAE.Stat SDMX"
INDUSTRY = "居民消费价格"
DATAFLOW = "FCSA:DF_CPI(3.2.0)"
DATA_URL = (
    "https://releaseeuaestat.fcsc.gov.ae/rest/data/"
    "FCSA,DF_CPI,3.2.0/all?startPeriod=2021-01"
    "&dimensionAtObservation=AllDimensions"
)
EXPLORER_URL = "https://uaestat.fcsc.gov.ae/"
ACCEPT_CSV = "application/vnd.sdmx.data+csv;version=2.0.0"

INDEX_INDICATORS = {
    "ALL": "阿联酋:消费者价格指数:总体(2021=100)",
    "FNB": "阿联酋:消费者价格指数:食品与饮料(2021=100)",
}
INDICATORS = {
    "ALL": "阿联酋:消费者价格指数:总体同比变化(%)",
    "FNB": "阿联酋:消费者价格指数:食品与饮料同比变化(%)",
}
INDEX_INDICATOR_ORDER = {
    name: index for index, name in enumerate(INDEX_INDICATORS.values())
}
INDICATOR_UNITS = {name: "%" for name in INDICATORS.values()}
LEGACY_INDICATORS = tuple(INDEX_INDICATORS.values())
_REQUIRED_COLUMNS = {
    "STRUCTURE_ID",
    "MEASURE",
    "UNIT_MEASURE",
    "REF_AREA",
    "FREQ",
    "CPI_DIV",
    "SOURCE_DETAIL",
    "TIME_PERIOD",
    "OBS_VALUE",
}


def _parse_period(value: str) -> date:
    """Parse an SDMX month and normalize it to calendar month-end."""

    try:
        month = datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError(f"FCSC CPI 时间格式异常：{value!r}") from exc
    return date(month.year, month.month, monthrange(month.year, month.month)[1])


def parse_cpi_csv(payload: bytes | str) -> list[dict]:
    """Validate the SDMX CSV and return national 2021-base CPI index rows."""

    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or ())
    missing = sorted(_REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"FCSC CPI SDMX CSV 缺少字段：{', '.join(missing)}")

    rows: list[dict] = []
    seen: set[tuple[date, str]] = set()
    for record in reader:
        division = record["CPI_DIV"]
        if not (
            record["STRUCTURE_ID"] == DATAFLOW
            and record["MEASURE"] == "CPI_INDEX21"
            and record["UNIT_MEASURE"] == "INDX"
            and record["REF_AREA"] == "AE"
            and record["FREQ"] == "M"
            and record["SOURCE_DETAIL"] == "FCSA"
            and division in INDEX_INDICATORS
        ):
            continue

        period = _parse_period(record["TIME_PERIOD"])
        indicator = INDEX_INDICATORS[division]
        key = (period, indicator)
        if key in seen:
            raise ValueError(f"FCSC CPI 存在重复观测：{period} / {indicator}")
        seen.add(key)
        try:
            value = float(record["OBS_VALUE"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"FCSC CPI 数值异常：{period} / {indicator}") from exc
        if not (value > 0):
            raise ValueError(f"FCSC CPI 指数必须为正数：{period} / {indicator}")
        rows.append({
            "period": period,
            "indicator": indicator,
            "value": value,
            "source_file": RAW_CSV.name,
        })

    if not rows:
        raise ValueError("FCSC CPI SDMX CSV 中没有全国月度 2021=100 指数")
    _validate_rows(rows)
    return sorted(
        rows,
        key=lambda row: (row["period"], INDEX_INDICATOR_ORDER[row["indicator"]]),
    )


def _parse_official_yoy_csv(payload: bytes | str) -> list[dict]:
    """Return published FCSC annual-change rows where the dataflow provides them."""

    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    reader = csv.DictReader(io.StringIO(text))
    missing = sorted(_REQUIRED_COLUMNS - set(reader.fieldnames or ()))
    if missing:
        raise ValueError(f"FCSC CPI SDMX CSV 缺少字段：{', '.join(missing)}")

    rows: list[dict] = []
    seen: set[tuple[date, str]] = set()
    for record in reader:
        division = record["CPI_DIV"]
        if not (
            record["STRUCTURE_ID"] == DATAFLOW
            and record["MEASURE"] == "CPI_ANNCHG21"
            and record["UNIT_MEASURE"] == "PERCENT"
            and record["REF_AREA"] == "AE"
            and record["FREQ"] == "M"
            and record["SOURCE_DETAIL"] == "FCSA"
            and division in INDICATORS
        ):
            continue

        period = _parse_period(record["TIME_PERIOD"])
        indicator = INDICATORS[division]
        key = (period, indicator)
        if key in seen:
            raise ValueError(f"FCSC CPI 存在重复同比观测：{period} / {indicator}")
        seen.add(key)
        try:
            value = float(record["OBS_VALUE"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"FCSC CPI 同比数值异常：{period} / {indicator}") from exc
        if not isfinite(value):
            raise ValueError(f"FCSC CPI 同比数值异常：{period} / {indicator}")
        rows.append({"period": period, "indicator": indicator, "value": value})
    return rows


def _month_sequence(first: date, last: date) -> list[date]:
    result = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        result.append(date(year, month, monthrange(year, month)[1]))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return result


def _validate_rows(rows: list[dict]) -> None:
    grouped = {
        indicator: sorted(row["period"] for row in rows if row["indicator"] == indicator)
        for indicator in INDEX_INDICATORS.values()
    }
    if any(not periods for periods in grouped.values()):
        raise ValueError("FCSC CPI 总体指数或食品与饮料指数缺失")
    if grouped[INDEX_INDICATORS["ALL"]] != grouped[INDEX_INDICATORS["FNB"]]:
        raise ValueError("FCSC CPI 总体指数与食品饮料指数期间不一致")
    periods = grouped[INDEX_INDICATORS["ALL"]]
    if periods != _month_sequence(periods[0], periods[-1]):
        raise ValueError("FCSC CPI 月度序列存在缺期")
    if periods[0] != date(2021, 1, 31) or len(periods) < 24:
        raise ValueError("FCSC CPI 月度历史过短或起始月份异常，拒绝更新数据库")
    if periods[-1] > date.today():
        raise ValueError("FCSC CPI 数据含未来月份，拒绝更新数据库")


def _validate_yoy_rows(rows: list[dict]) -> None:
    grouped = {
        indicator: sorted(row["period"] for row in rows if row["indicator"] == indicator)
        for indicator in INDICATORS.values()
    }
    if any(not periods for periods in grouped.values()):
        raise ValueError("FCSC CPI 总体或食品与饮料同比序列缺失")
    if grouped[INDICATORS["ALL"]] != grouped[INDICATORS["FNB"]]:
        raise ValueError("FCSC CPI 总体与食品饮料同比期间不一致")
    periods = grouped[INDICATORS["ALL"]]
    if periods != _month_sequence(periods[0], periods[-1]):
        raise ValueError("FCSC CPI 同比月度序列存在缺期")
    if periods[0] != date(2022, 1, 31) or len(periods) < 24:
        raise ValueError("FCSC CPI 同比历史过短，拒绝更新数据库")
    if periods[-1] > date.today():
        raise ValueError("FCSC CPI 同比数据含未来月份，拒绝更新数据库")


def _download_csv(*, force: bool) -> str:
    """Refresh the small live SDMX CSV on every online update."""

    # The endpoint is a small mutable national dataflow; always refresh it so
    # a cached raw file cannot silently hide newly released monthly values.
    del force
    return download_file(
        DATA_URL,
        RAW_CSV,
        force=True,
        min_bytes=1024,
        referer=EXPLORER_URL,
        headers={"Accept": ACCEPT_CSV},
        browser_transport=True,
    )


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": name,
            "frequency": "月",
            "unit": INDICATOR_UNITS[name],
            "source": SOURCE_NAME,
            "type": "指标",
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name in INDICATORS.values()
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Fetch CPI index levels, calculate YoY rates, and replace report rows."""

    download_note = ""
    if not skip_download:
        _download_csv(force=force)
        download_note = "已在线刷新 FCSC UAE.Stat SDMX"
    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"FCSC CPI 原始 CSV 不存在：{RAW_CSV}")

    payload = RAW_CSV.read_bytes()
    rows = parse_cpi_csv(payload)
    official_yoy_values = {
        (row["indicator"], row["period"]): row["value"]
        for row in _parse_official_yoy_csv(payload)
    }
    latest = max(row["period"] for row in rows)
    existing_latest = con.execute("SELECT max(period) FROM fcsc_monthly").fetchone()[0]
    if existing_latest is not None and latest < existing_latest:
        raise ValueError(
            f"FCSC API 最新月份 {latest} 早于库中已有月份 {existing_latest}，拒绝回退"
        )

    index_values = {
        indicator: {row["period"]: row["value"] for row in rows
                    if row["indicator"] == indicator}
        for indicator in INDEX_INDICATORS.values()
    }
    yoy_rows = []
    for division, index_indicator in INDEX_INDICATORS.items():
        target_indicator = INDICATORS[division]
        for period, index_value in index_values[index_indicator].items():
            prior_period = date(
                period.year - 1,
                period.month,
                monthrange(period.year - 1, period.month)[1],
            )
            previous = index_values[index_indicator].get(prior_period)
            if previous is None:
                continue
            value = official_yoy_values.get((target_indicator, period))
            if value is None:
                # FCSC omits its published annual-change measure for 2022. Fill
                # that gap from the same official index series at its 2-decimal
                # published precision; prefer FCSC's native rate otherwise.
                value = round((index_value / previous - 1) * 100, 2)
            yoy_rows.append({
                "period": period,
                "indicator": target_indicator,
                "value": value,
                "source_file": RAW_CSV.name,
            })
    _validate_yoy_rows(yoy_rows)

    con.execute("DELETE FROM fcsc_monthly")
    con.executemany(
        "INSERT INTO fcsc_monthly (period, indicator, value, source_file) "
        "VALUES (?, ?, ?, ?)",
        [
            (row["period"], row["indicator"], row["value"], row["source_file"])
            for row in yoy_rows
        ],
    )
    con.execute(
        "DELETE FROM meta_indicator_dictionary WHERE indicator_name IN (?, ?)",
        list(LEGACY_INDICATORS),
    )
    db.upsert_dictionary_rows(con, _dictionary_rows())

    periods = sorted({row["period"] for row in yoy_rows})
    note = (
        f"{len(periods)} 个月 × {len(INDICATORS)} 项同比指标 "
        f"（{periods[0]:%Y-%m} 至 {periods[-1]:%Y-%m}）"
    )
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(yoy_rows), "note": note}


def _sheet_spec(con) -> dict:
    records = con.execute(
        "SELECT period, indicator, value FROM fcsc_monthly ORDER BY period"
    ).fetchall()
    by_period: dict[date, dict[str, float | None]] = {}
    for period, indicator, value in records:
        by_period.setdefault(period, {})[indicator] = None if value is None else float(value)
    rows = [
        (period, by_period[period])
        for period in sorted(by_period)
    ]
    return {
        "name": TARGET_SHEET,
        "title": "联邦竞争力与统计中心消费者价格同比变化",
        "indicators": list(INDICATORS.values()),
        "rows": rows,
    }


def merge(workbook_path: Path) -> dict:
    """Write FCSC national CPI series from DuckDB into ``月度_FCSC``."""

    return merge_source_sheet(workbook_path, _sheet_spec)


__all__ = [
    "DATA_URL",
    "INDICATORS",
    "LEGACY_INDICATORS",
    "RAW_CSV",
    "SOURCE_NAME",
    "TARGET_SHEET",
    "_sheet_spec",
    "merge",
    "parse_cpi_csv",
    "update",
]
