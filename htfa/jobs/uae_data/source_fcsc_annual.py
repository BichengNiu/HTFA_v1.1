"""FCSC annual investment: official observations → DuckDB → report workbook."""

import csv
from datetime import date
import io
import json
import math
from pathlib import Path

from . import db
from ._official_download import download_file
from .paths import DATA_DIR
from .workbook_sheet_writer import write_indicator_sheets

SOURCE = "FCSC UAE.Stat"
TABLE = "fcsc_investment_annual"
DATASETS = (
    "DF_NA_FIX_CUR", "DF_NA_EXPEND_CUR", "DF_NA_EXPEND_CON",
    "DF_FI_TYPE", "DF_FI_ECON_ACTIV", "DF_FI_COUNTRY",
)
SHEETS = (
    "年度_资本形成", "年度_行业资本形成", "年度_外资类型",
    "年度_外资行业", "年度_外资来源国",
)
INDUSTRIES = dict(zip(
    ("A", "B", "C", "DE", "F", "G", "H", "I", "J", "K", "L", "MN", "O", "P", "Q", "RS"),
    ("农业林业渔业", "采矿及油气", "制造业", "公用事业及废物管理", "建筑业", "批发零售",
     "运输仓储", "住宿餐饮", "信息通信", "金融保险", "房地产", "专业技术及行政支持",
     "公共行政国防", "教育", "卫生及社会工作", "文娱及其他服务"),
))
FDI_INDUSTRIES = {
    **INDUSTRIES, "D": "电力燃气", "E": "供水及废物管理", "M": "专业科技活动",
    "N": "行政支持服务", "R": "文娱活动", "S": "其他服务",
}
FOREIGN_TYPES = {"FI": "外国投资总额", "FDI": "外商直接投资", "PORT": "外国证券投资", "OTH": "其他外国投资"}


def data_url(dataset):
    return (f"https://releaseeuaestat.fcsc.gov.ae/rest/data/FCSA,{dataset}/all"
            "?dimensionAtObservation=AllDimensions")


def parse_csv(payload: bytes, dataset: str) -> list[tuple]:
    """Keep source units and dimension keys; reject nonannual or duplicate rows."""
    if dataset not in DATASETS:
        raise ValueError(f"Unknown annual dataset: {dataset}")
    rows, seen = [], set()
    for record in csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))):
        if record["REF_AREA"] != "AE" or record["FREQ"] != "A":
            raise ValueError("年度投资数据的地区或频率异常")
        if not record["DATAFLOW"].startswith(f"FCSA:{dataset}("):
            raise ValueError("年度投资数据集身份不匹配")
        year = int(record["TIME_PERIOD"])
        expected_unit = "AED" if dataset.startswith("DF_FI") else "MILAED"
        if record["UNIT_MEASURE"] != expected_unit or not 1900 <= year <= date.today().year:
            raise ValueError("年度投资数据单位或年份异常")
        if not record["OBS_VALUE"].strip():
            continue
        value = float(record["OBS_VALUE"])
        if not math.isfinite(value) or record.get("UNIT_MULT", "") not in ("", "0"):
            raise ValueError("年度投资数据数值或倍率异常")
        measure = record["EXPEND"] if dataset.startswith("DF_NA_EXPEND") else record["MEASURE"]
        activity = record.get("ISIC", record.get("ECON_ACTIV", "_T"))
        country = record.get("COUNTRY", "_T")
        key = (dataset, date(year, 12, 31), measure, activity, country)
        if key in seen:
            raise ValueError(f"年度投资重复观测: {key}")
        seen.add(key)
        rows.append((*key, value, expected_unit, data_url(dataset)))
    if not rows:
        raise ValueError(f"年度投资表为空: {dataset}")
    return rows


def _indicator(sheet, label):
    return f"{sheet}:{label}"


def sheet_specs(con):
    """Build report sheets entirely from the authoritative observation table."""
    countries = json.loads(Path(__file__).with_name("fcsc_country_labels.json").read_text())
    countries.update({"826": "英国", "356": "印度", "840": "美国", "756": "瑞士",
                      "682": "沙特阿拉伯", "250": "法国", "528": "荷兰", "999": "其他来源地"})
    series = {sheet: {} for sheet in SHEETS}
    for dataset, period, measure, activity, country, value, unit in con.execute(
        f"SELECT dataset,period,measure,activity,country,value,unit FROM {TABLE} ORDER BY period"
    ).fetchall():
        sheet = label = None
        if dataset.startswith("DF_NA_EXPEND") and measure == "EXPEND4":
            sheet = SHEETS[0]
            label = "资本形成总额（现价）" if dataset.endswith("CUR") else "资本形成总额（2010年不变价）"
        elif dataset == "DF_NA_FIX_CUR" and activity in INDUSTRIES:
            sheet, label = SHEETS[1], INDUSTRIES[activity]
        elif dataset == "DF_FI_TYPE" and measure in FOREIGN_TYPES:
            sheet, label = SHEETS[2], FOREIGN_TYPES[measure]
        elif dataset == "DF_FI_ECON_ACTIV" and measure == "FDI" and activity in FDI_INDUSTRIES:
            sheet, label = SHEETS[3], FDI_INDUSTRIES[activity]
        elif dataset == "DF_FI_COUNTRY" and activity == "_T" and country != "_T":
            sheet, label = SHEETS[4], countries.get(country, country)
        if sheet is None:
            continue
        name = _indicator(sheet, label)
        observations = series[sheet].setdefault(period, {})
        if name in observations:
            raise ValueError(f"年度报告列名冲突: {name}")
        observations[name] = value / (1000 if unit == "MILAED" else 1e9)
    specs = []
    for sheet, periods in series.items():
        if not periods:
            raise ValueError(f"年度报告缺少数据: {sheet}")
        names = sorted({name for values in periods.values() for name in values})
        specs.append({"name": sheet, "title": sheet, "indicators": names,
                      "metadata": {name: {"frequency": "年", "unit": "十亿迪拉姆", "source": SOURCE}
                                   for name in names}, "rows": list(periods.items())})
    return specs


def update(con, *, force=False, skip_download=False):
    rows = []
    for dataset in DATASETS:
        path = DATA_DIR / "raw" / "fcsc_annual" / f"{dataset}.csv"
        if not skip_download:
            download_file(data_url(dataset), path, force=True, browser_transport=True,
                          headers={"Accept": "text/csv;version=2.0.0"})
        rows.extend(parse_csv(path.read_bytes(), dataset))
    with db.transaction(con):
        con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (dataset VARCHAR, period DATE, "
                    "measure VARCHAR, activity VARCHAR, country VARCHAR, value DOUBLE, "
                    "unit VARCHAR, source_url VARCHAR, PRIMARY KEY(dataset,period,measure,activity,country))")
        for dataset, first, last in con.execute(
            f"SELECT dataset,min(period),max(period) FROM {TABLE} GROUP BY dataset"
        ).fetchall():
            periods = [r[1] for r in rows if r[0] == dataset]
            if not periods or min(periods) > first or max(periods) < last:
                raise ValueError(f"年度数据覆盖回退: {dataset}")
        con.execute(f"DELETE FROM {TABLE}")
        con.executemany(f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?)", rows)
        specs = sheet_specs(con)
        db.upsert_dictionary_rows(con, [
            {"indicator_name": name, "frequency": "年", "unit": "十亿迪拉姆", "source": SOURCE,
             "type": "指标", "industry": "年度投资", "updated_at": date.today()}
            for spec in specs for name in spec["indicators"]
        ])
    return {"status": "ok", "rows": len(rows), "note": "年度资本形成及历史外资已入库"}


def merge(workbook_path):
    with db.connect(read_only=True) as con:
        specs = sheet_specs(con)
    counts = write_indicator_sheets(workbook_path, specs)
    return {"status": "ok", "rows": sum(counts.values()), "note": "年度数据已从 DuckDB 同步"}
