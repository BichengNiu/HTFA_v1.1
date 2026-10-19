"""FCSC quarterly GDP and industry value added, with separate price releases."""

from __future__ import annotations

import csv
import io
from calendar import monthrange
from datetime import date
from math import isfinite
from pathlib import Path

from . import db
from ._official_download import download_file
from .paths import DATA_DIR
from .workbook_sheet_writer import merge_source_columns


RAW_DIR = DATA_DIR / "raw" / "fcsc_gdp"
TARGET_SHEET = "季度_Wind"
SOURCE_NAME = "FCSC UAE.Stat Quarterly National Accounts"
TABLE = "fcsc_gdp_quarterly"
MEASURES = {
    "TOT_GDP": "", "TOT_NO": ":非石油", "NFC": ":非金融公司",
    "AGR": ":农业、林业和渔业", "MAN": ":制造业",
    "ELE": ":电力、煤气、供水及废物管理", "CON": ":建筑业",
    "WHO": ":批发零售业、汽车及摩托车修理", "TRA": ":运输和仓储",
    "ACC": ":住宿和餐饮服务业", "INF": ":信息和通信", "FIN": ":金融保险业",
    "REA": ":房地产业", "PRO": ":专业、科技活动",
    "PUB": ":公共行政和国防、强制性社会保障", "EDU": ":教育类",
    "HUM": ":人类健康和社会工作活动", "ART": ":艺术、娱乐及其他服务活动",
    "ACT": ":家庭作为雇主的活动",
}
PRICE_SYSTEMS = {"CON": "不变价", "CUR": "现价"}
RATE_MEASURES = {"TOT_GDP", "TOT_NO", "NFC"}
DATA_URLS = {
    system: f"https://releaseeuaestat.fcsc.gov.ae/rest/data/FCSA,DF_QGDP_{system}/all"
            "?dimensionAtObservation=AllDimensions"
    for system in PRICE_SYSTEMS
}


def _name(system: str, measure: str, kind: str = "VAL") -> str:
    name = f"阿联酋:GDP:{PRICE_SYSTEMS[system]}{MEASURES[measure]}"
    return name + (":当季同比" if kind == "GWTH_RATE" else "")


INDICATORS = {
    _name(system, measure, kind): (
        "%" if kind == "GWTH_RATE" else "十亿阿联酋迪拉姆", SOURCE_NAME,
    )
    for system in PRICE_SYSTEMS
    for measure in MEASURES
    for kind in (["VAL", "GWTH_RATE"] if measure in RATE_MEASURES else ["VAL"])
}


def parse_gdp_csv(payload: bytes, system: str) -> list[dict]:
    """Validate official quarters and retain levels and published annual rates."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    required = {"REF_AREA", "FREQ", "SOURCE_DETAIL", "QGDP_SYS", "QGDP_UNIT",
                "UNIT_MEASURE", "MEASURE", "TIME_PERIOD", "QUARTER", "OBS_VALUE"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("FCSC GDP CSV 缺少必要维度")
    values = {}
    for record in reader:
        if record["REF_AREA"] != "AE" or record["SOURCE_DETAIL"] != "FCSC":
            continue
        if record["FREQ"] != "Q" or record["QGDP_SYS"] != system:
            raise ValueError("FCSC GDP 频率或价格口径不匹配")
        measure, kind = record["MEASURE"], record["QGDP_UNIT"]
        if measure not in {*MEASURES, "MIN"} or kind not in {"VAL", "GWTH_RATE"}:
            raise ValueError(f"FCSC GDP 未识别的维度：{measure}/{kind}")
        expected_unit = "MILAED" if kind == "VAL" else "PERCENT"
        if record["UNIT_MEASURE"] != expected_unit:
            raise ValueError("FCSC GDP 单位不匹配")
        quarter = record["QUARTER"]
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise ValueError(f"FCSC GDP 季度异常：{quarter}")
        year, month = int(record["TIME_PERIOD"]), int(quarter[1]) * 3
        period = date(year, month, monthrange(year, month)[1])
        value = float(record["OBS_VALUE"])
        if period > date.today() or not isfinite(value) or (kind == "VAL" and value <= 0):
            raise ValueError("FCSC GDP 观测日期或数值异常")
        key = (period, measure, kind)
        if key in values:
            raise ValueError(f"FCSC GDP 重复观测：{key}")
        values[key] = value
    periods = sorted({key[0] for key in values})
    if not periods:
        raise ValueError("FCSC GDP 无有效观测")
    quarter_ids = [p.year * 4 + (p.month // 3 - 1) for p in periods]
    if quarter_ids != list(range(quarter_ids[0], quarter_ids[-1] + 1)):
        raise ValueError("FCSC GDP 季度序列缺期")
    for period in periods:
        needed = [(m, "VAL") for m in [*MEASURES, "MIN"]]
        has_rates = any((period, m, "GWTH_RATE") in values for m in RATE_MEASURES)
        if period.year * 4 + period.month // 3 - 1 >= quarter_ids[0] + 4 or has_rates:
            needed += [(m, "GWTH_RATE") for m in RATE_MEASURES]
        if any((period, m, k) not in values for m, k in needed):
            raise ValueError(f"FCSC GDP 指标缺失：{period}")
        total = values[period, "TOT_GDP", "VAL"]
        nonoil = values[period, "TOT_NO", "VAL"]
        mining = values[period, "MIN", "VAL"]
        industry_sum = sum(values[period, m, "VAL"] for m in MEASURES
                           if m not in RATE_MEASURES)
        # Historical values are rounded to million AED: each of the 17 terms
        # (16 industries and their total) can contribute half a million AED.
        if abs(industry_sum - nonoil) > 8.5 or abs(total - nonoil - mining) > 1.5:
            raise ValueError(f"FCSC GDP 分项加总超出公布精度：{period}")
    return [
        {"period": period, "indicator": _name(system, measure, kind),
         "value": value / 1000 if kind == "VAL" else value,
         "source_url": DATA_URLS[system], "source_file": f"{system}.csv"}
        for (period, measure, kind), value in sorted(values.items())
        if measure in MEASURES and (kind == "VAL" or measure in RATE_MEASURES)
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Fetch both price systems and atomically upsert all 44 report indicators."""
    rows = []
    for system, url in DATA_URLS.items():
        path = RAW_DIR / f"{system}.csv"
        if not skip_download:
            download_file(url, path, force=True, browser_transport=True,
                          headers={"Accept": "text/csv;version=2.0.0;labels=both"})
        rows.extend(parse_gdp_csv(path.read_bytes(), system))
    with db.transaction(con):
        con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (period DATE, "
                    "indicator VARCHAR, value DOUBLE, source_url VARCHAR, "
                    "source_file VARCHAR, PRIMARY KEY(period,indicator))")
        for indicator, start, end in con.execute(
            f"SELECT indicator,min(period),max(period) FROM {TABLE} GROUP BY 1"
        ).fetchall():
            periods = [r["period"] for r in rows if r["indicator"] == indicator]
            if not periods or min(periods) > start or max(periods) < end:
                raise ValueError(f"FCSC GDP 数据覆盖回退：{indicator}")
        con.executemany(f"INSERT OR REPLACE INTO {TABLE} VALUES (?,?,?,?,?)", [
            (r["period"], r["indicator"], r["value"], r["source_url"], r["source_file"])
            for r in rows
        ])
        db.upsert_dictionary_rows(con, [
            {"indicator_name": name, "frequency": "季", "unit": unit,
             "source": source, "type": "指标", "industry": "国民经济核算",
             "updated_at": date.today()}
            for name, (unit, source) in INDICATORS.items()
        ])
    return {"status": "ok", "rows": len(rows), "note": "44 项季度 GDP 指标已入库"}


def merge(workbook_path: Path) -> dict:
    """Patch GDP columns from DuckDB and atomically preserve the rest of the workbook."""
    return merge_source_columns(workbook_path, _sheet_spec)


def _sheet_spec(con) -> dict:
    return {
        "name": TARGET_SHEET, "indicators": list(INDICATORS),
        "observations": con.execute(
            f"SELECT period,indicator,value FROM {TABLE} ORDER BY period"
        ).fetchall(),
    }
