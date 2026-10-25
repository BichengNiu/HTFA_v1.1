"""Harmonized six-country annual GDP and sector shares from World Bank WDI."""

from datetime import date
import json
import math

import pandas as pd

from htfa.monitoring.uae.annual_comparison_contracts import (
    COUNTRIES, GDP_LEVEL, GDP_GROWTH, SECTOR_INDICATORS, GDP_SHEET, GCC_NAME,
    LEVEL_SUFFIX, GROWTH_SUFFIX, REPORT_UNITS,
)
from . import db
from .paths import DATA_DIR
from ._official_download import download_file
from .workbook_sheet_writer import write_indicator_sheets

TABLE = "wdi_gcc_annual"
SOURCE = "World Bank World Development Indicators"
INDICATORS = (GDP_LEVEL, GDP_GROWTH, *SECTOR_INDICATORS)


def data_url(indicator):
    countries = ";".join(COUNTRIES)
    return (f"https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
            f"?format=json&per_page=1000&date=1960:{date.today().year - 1}&source=2")


def parse_payload(payload, indicator):
    """Validate WDI pagination, identity and dimensions; retain reported nulls."""
    if indicator not in INDICATORS:
        raise ValueError("未知 WDI 指标")
    data = json.loads(payload)
    if not isinstance(data, list) or len(data) != 2 or not isinstance(data[0], dict) or not isinstance(data[1], list):
        raise ValueError("WDI 响应结构异常")
    metadata, observations = data
    if metadata.get("pages") != 1 or metadata.get("page") != 1 or metadata.get("total") != len(observations) or str(metadata.get("sourceid")) != "2":
        raise ValueError("WDI 分页不完整或来源不是 WDI")
    updated_at = date.fromisoformat(metadata["lastupdated"])
    rows, seen, countries = [], set(), set()
    for observation in observations:
        country = observation["countryiso3code"]
        if country not in COUNTRIES or observation["indicator"]["id"] != indicator:
            raise ValueError("WDI 国家或指标身份异常")
        year = int(observation["date"])
        value = observation["value"]
        if not 1960 <= year <= date.today().year or observation.get("decimal") is None:
            raise ValueError("WDI 年份或精度异常")
        if value is not None:
            value = float(value)
            if not math.isfinite(value) or (indicator == GDP_LEVEL and value <= 0):
                raise ValueError("WDI GDP 数值异常")
            if indicator in SECTOR_INDICATORS and not 0 <= value <= 100:
                raise ValueError("WDI 产业占比异常")
        key = (country, indicator, date(year, 12, 31))
        if key in seen:
            raise ValueError("WDI 重复年度观测")
        seen.add(key)
        countries.add(country)
        rows.append((*key, value, data_url(indicator), updated_at))
    if countries != set(COUNTRIES) or not any(row[3] is not None for row in rows):
        raise ValueError("WDI 六国覆盖不完整或无有效观测")
    return rows


def comparison_frames(con):
    """Average six complete country observations, never a changing subset."""
    rows = con.execute(f"SELECT country,indicator,period,value FROM {TABLE}").df()
    frames = {}
    for indicator in INDICATORS:
        subset = rows[rows.indicator == indicator]
        pivot = subset.pivot(index="period", columns="country", values="value").reindex(columns=list(COUNTRIES))
        pivot[GCC_NAME] = pivot.mean(axis=1).where(pivot.notna().sum(axis=1) == len(COUNTRIES))
        pivot = pivot.rename(columns=COUNTRIES)
        if indicator == GDP_LEVEL:
            frames[GDP_SHEET] = (pivot / 1e9).add_suffix(LEVEL_SUFFIX)
        elif indicator == GDP_GROWTH:
            frames[GDP_SHEET] = frames[GDP_SHEET].join(pivot.add_suffix(GROWTH_SUFFIX), how="outer")
        else:
            frames[SECTOR_INDICATORS[indicator][0]] = pivot
    return {sheet: frame.dropna(how="all").sort_index() for sheet, frame in frames.items()}


def sheet_specs(con):
    specs = []
    for sheet, frame in comparison_frames(con).items():
        names = [f"{sheet}:{name}" for name in frame]
        metadata = {f"{sheet}:{name}": {"frequency": "年", "unit": REPORT_UNITS[sheet][name], "source": SOURCE} for name in frame}
        rows = [(period.to_pydatetime(), {f"{sheet}:{name}": None if pd.isna(value) else float(value)
                 for name, value in values.items()}) for period, values in frame.iterrows()]
        specs.append({"name": sheet, "title": sheet, "indicators": names, "metadata": metadata, "rows": rows})
    return specs


def update(con, *, force=False, skip_download=False):
    rows = []
    for indicator in INDICATORS:
        path = DATA_DIR / "raw" / "wdi_gcc" / f"{indicator}.json"
        if not skip_download:
            download_file(data_url(indicator), path, force=True)
        rows.extend(parse_payload(path.read_bytes(), indicator))
    with db.transaction(con):
        con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (country VARCHAR, indicator VARCHAR, period DATE, "
                    "value DOUBLE, source_url VARCHAR, updated_at DATE, PRIMARY KEY(country,indicator,period))")
        for country, indicator, first, last in con.execute(
            f"SELECT country,indicator,min(period),max(period) FROM {TABLE} WHERE value IS NOT NULL GROUP BY 1,2"
        ).fetchall():
            periods = [row[2] for row in rows if row[0] == country and row[1] == indicator and row[3] is not None]
            if not periods or min(periods) > first or max(periods) < last:
                raise ValueError(f"WDI 有效观测覆盖回退: {country}/{indicator}")
        con.execute(f"DELETE FROM {TABLE}")
        con.executemany(f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?)", rows)
        specs = sheet_specs(con)
        db.upsert_dictionary_rows(con, [
            {"indicator_name": name, "frequency": "年", "unit": spec["metadata"][name]["unit"],
             "source": SOURCE, "type": "指标", "industry": "年度国民账户", "updated_at": date.today()}
            for spec in specs for name in spec["indicators"]
        ])
    return {"status": "ok", "rows": len(rows), "note": "六国年度 GDP 与三次产业占比已入库；仅完整六国计算均值"}


def merge(workbook_path):
    with db.connect(read_only=True) as con:
        specs = sheet_specs(con)
    counts = write_indicator_sheets(workbook_path, specs)
    return {"status": "ok", "rows": sum(counts.values()), "note": "年度 GCC 对比已从 DuckDB 同步"}
