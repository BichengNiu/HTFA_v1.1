"""EIA UAE petroleum and other liquids production for the macro report."""

from __future__ import annotations

import json
import os
import tempfile
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from math import isfinite
from pathlib import Path

from . import db
from .paths import DATA_DIR
from .workbook_sheet_writer import merge_source_columns


RAW_PATH = DATA_DIR / "raw" / "eia_liquids" / "monthly.json"
DATA_URL = "https://api.eia.gov/v2/international/data/"
INDICATOR = "阿联酋:产量:石油及其他液体"
SOURCE_NAME = "U.S. EIA International Energy Statistics (product 53, production)"


def parse_monthly(payload: dict) -> list[tuple]:
    """Validate scope and continuous monthly observations, converting TBPD to million b/d."""
    response = payload["response"]
    records = response["data"]
    if not records or int(response["total"]) != len(records):
        raise ValueError("EIA 数据为空或分页未完整下载")
    rows = {}
    for item in records:
        scope = tuple(str(item.get(key)) for key in (
            "countryRegionId", "productId", "activityId", "unit",
        ))
        if scope != ("ARE", "53", "1", "TBPD"):
            raise ValueError("EIA 国家、石油及其他液体定义、产量或单位不匹配")
        period = datetime.strptime(item["period"], "%Y-%m").date()
        period = period.replace(day=monthrange(period.year, period.month)[1])
        value = float(item["value"]) / 1000
        if period > date.today() or not isfinite(value) or value < 0:
            raise ValueError("EIA 观测日期或产量异常")
        if period in rows:
            raise ValueError("EIA 存在重复月份")
        rows[period] = (period, value, item.get("dataFlagId"))
    periods = sorted(rows)
    months = [p.year * 12 + p.month for p in periods]
    if months != list(range(months[0], months[-1] + 1)):
        raise ValueError("EIA 月度序列缺期")
    return [rows[period] for period in periods]


def quarterly_observations(monthly: list[tuple]) -> list[tuple]:
    """Average monthly production rates by calendar days; omit incomplete quarters."""
    groups = defaultdict(list)
    for period, value, _flag in monthly:
        month = ((period.month - 1) // 3 + 1) * 3
        quarter = date(period.year, month, monthrange(period.year, month)[1])
        groups[quarter].append((period.day, value))
    return [
        (period, sum(days * value for days, value in values) / sum(d for d, _ in values))
        for period, values in sorted(groups.items()) if len(values) == 3
    ]


def _download() -> None:
    from curl_cffi import requests

    params = {
        "api_key": os.environ.get("HTFA_EIA_API_KEY", "").strip() or "DEMO_KEY",
        "frequency": "monthly", "data[0]": "value",
        "facets[countryRegionId][]": "ARE", "facets[productId][]": "53",
        "facets[activityId][]": "1", "facets[unit][]": "TBPD",
        "start": "1993-01", "sort[0][column]": "period",
        "sort[0][direction]": "asc", "length": 5000,
    }
    try:
        response = requests.get(DATA_URL, params=params, impersonate="chrome", timeout=45)
    except requests.RequestsError:
        raise RuntimeError("EIA 月度产量下载失败") from None
    if response.status_code != 200:
        raise RuntimeError(f"EIA 月度产量下载失败（HTTP {response.status_code}）")
    payload = response.json()
    parse_monthly(payload)
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=RAW_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        os.replace(name, RAW_PATH)
    finally:
        Path(name).unlink(missing_ok=True)


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Atomically store monthly source data and complete quarterly production rates."""
    if not skip_download:
        _download()
    monthly = parse_monthly(json.loads(RAW_PATH.read_text(encoding="utf-8")))
    quarterly = quarterly_observations(monthly)
    if not quarterly:
        raise ValueError("EIA 没有完整季度")
    con.begin()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS eia_liquids_monthly ("
                    "period DATE PRIMARY KEY, production_mbd DOUBLE, data_flag VARCHAR)")
        con.execute("CREATE TABLE IF NOT EXISTS eia_liquids_quarterly ("
                    "period DATE PRIMARY KEY, production_mbd DOUBLE)")
        for table, records in [("eia_liquids_monthly", monthly),
                               ("eia_liquids_quarterly", quarterly)]:
            start, end = con.execute(f"SELECT min(period),max(period) FROM {table}").fetchone()
            if start is not None and (records[0][0] > start or records[-1][0] < end):
                raise ValueError(f"EIA 数据覆盖回退：{table}")
            placeholders = ",".join("?" for _ in records[0])
            con.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", records)
        db.upsert_dictionary_rows(con, [{
            "indicator_name": INDICATOR, "frequency": "季", "unit": "百万桶/天",
            "source": SOURCE_NAME, "type": "指标", "industry": "能源",
            "updated_at": date.today(),
        }])
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return {"status": "ok", "rows": len(monthly) + len(quarterly),
            "note": f"EIA 石油及其他液体产量，最新完整季度 {quarterly[-1][0]}"}


def merge(workbook_path: Path) -> dict:
    """Update the macro report's all-liquids column using only DuckDB observations."""
    return merge_source_columns(workbook_path, _sheet_spec)


def _sheet_spec(con) -> dict:
    return {
        "name": "季度_Wind", "indicators": [INDICATOR],
        "observations": con.execute(
            "SELECT period,?,production_mbd FROM eia_liquids_quarterly ORDER BY period",
            [INDICATOR],
        ).fetchall(),
    }
