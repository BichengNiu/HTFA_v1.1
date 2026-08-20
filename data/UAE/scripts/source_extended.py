"""Write all UAE DuckDB indicator series that were previously DB-only."""

from __future__ import annotations

import calendar
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
from workbook_sheet_writer import write_indicator_sheets  # noqa: E402

EUROSTAT_SHEET = "月度_Eurostat航空"
DOT_SHEET = "月度_DOTT100"
DUBAI_CUSTOMS_SHEET = "月度_迪拜海关航空"
SALIK_SHEET = "季度_Salik"
EMPLOYMENT_SHEET = "月度_工作搜索热度"
COMTRADE_SHEET = "月度_UNComtrade"
VEHICLES_SHEET = "月度_汽车进口"
DED_SHEET = "月度_DED"
FOREIGN_LABOUR_SHEET = "月度_外籍劳动力"


def _metadata(con, names: list[str]) -> dict[str, dict[str, Any]]:
    records = con.execute(
        "SELECT indicator_name, frequency, unit, source "
        "FROM meta_indicator_dictionary"
    ).fetchall()
    by_name = {
        row[0]: {
            "frequency": row[1],
            "unit": row[2],
            "source": row[3],
        }
        for row in records
    }
    missing = [name for name in names if name not in by_name]
    if missing:
        raise ValueError(f"数据库指标字典缺少：{', '.join(missing)}")
    return {name: by_name[name] for name in names}


def _month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def _eurostat(con) -> dict[str, Any]:
    datasets = {
        "avia_paexcc": "EU27↔阿联酋航空旅客",
        "avia_goexcc": "EU27↔阿联酋航空货运与邮件",
    }
    measures = {
        "PAS_BRD": "机上旅客数(人)",
        "PAS_BRD_ARR": "机上旅客数-抵达(人)",
        "PAS_BRD_DEP": "机上旅客数-离港(人)",
        "PAS_CRD": "载客数(人)",
        "PAS_CRD_ARR": "载客数-抵达(人)",
        "PAS_CRD_DEP": "载客数-离港(人)",
        "FRM_BRD": "机上货运与邮件(吨)",
        "FRM_BRD_ARR": "机上货运与邮件-抵达(吨)",
        "FRM_BRD_DEP": "机上货运与邮件-离港(吨)",
        "FRM_LD_NLD": "货运与邮件装+卸(吨)",
        "FRM_LD": "货运与邮件装载(吨)",
        "FRM_NLD": "货运与邮件卸载(吨)",
    }
    indicators = [
        f"{datasets[dataset]}:{measures[measure]}"
        for dataset in datasets
        for measure in measures
        if (dataset == "avia_paexcc") == measure.startswith("PAS")
    ]
    rows = _long_to_wide(
        con.execute(
            "SELECT period, dataset, tra_meas, value "
            "FROM eurostat_air_monthly "
            "WHERE geo = 'EU27_2020' AND partner = 'AE' AND schedule = 'TOTAL'"
        ).fetchall(),
        lambda dataset, measure: f"{datasets[dataset]}:{measures[measure]}",
        period_transform=_month_end,
    )
    return {"name": EUROSTAT_SHEET, "title": "Eurostat EU27↔阿联酋航空月度指标", "indicators": indicators, "rows": rows}


def _dot(con) -> dict[str, Any]:
    indicators = [
        "美国↔阿联酋_航空旅客_合计(人次)",
        "美国↔阿联酋_航空旅客_美→阿(人次)",
        "美国↔阿联酋_航空旅客_阿→美(人次)",
        "美国↔阿联酋_航空货运_合计(磅)",
        "美国↔阿联酋_航空货运_美→阿(磅)",
        "美国↔阿联酋_航空货运_阿→美(磅)",
        "美国↔阿联酋_航空邮件_合计(磅)",
        "美国↔阿联酋_航空邮件_美→阿(磅)",
        "美国↔阿联酋_航空邮件_阿→美(磅)",
        "美国↔阿联酋_执行航班_合计(班次)",
    ]
    rows = _long_to_wide(
        con.execute("SELECT period, indicator, value FROM dot_t100_monthly").fetchall(),
        lambda indicator: indicator,
        period_transform=_month_end,
    )
    return {"name": DOT_SHEET, "title": "US DOT T-100 美国↔阿联酋月度航空指标", "indicators": indicators, "rows": rows}


def _dubai_customs(con) -> dict[str, Any]:
    indicators = [
        "迪拜航空货运_进口总量(吨)", "迪拜航空货运_出口总量(吨)",
        "迪拜航空货运_转运总量(吨)", "迪拜航空货运_境内总量(吨)",
        "迪拜航空货运_合计总量(吨)", "迪拜航空货运_进口件数(件)",
        "迪拜航空货运_出口件数(件)", "迪拜航空货运_合计件数(件)",
        "迪拜航空货运_进口运单数(张)", "迪拜航空货运_出口运单数(张)",
        "迪拜航空货运_合计运单数(张)", "迪拜航空货运_进口体积(立方米)",
        "迪拜航空货运_出口体积(立方米)",
    ]
    rows = _long_to_wide(
        con.execute("SELECT period, indicator, value FROM dubai_airway_bill_monthly").fetchall(),
        lambda indicator: indicator,
        period_transform=_month_end,
    )
    return {"name": DUBAI_CUSTOMS_SHEET, "title": "迪拜海关航空货运月度指标", "indicators": indicators, "rows": rows}


def _salik(con) -> dict[str, Any]:
    indicator = "阿联酋:Salik注册活跃车辆:季末值"
    rows = [(period, {indicator: value}) for period, value in con.execute(
        "SELECT period, value FROM salik_active_vehicles_quarterly ORDER BY period"
    ).fetchall()]
    return {"name": SALIK_SHEET, "title": "Salik 注册活跃车辆季度指标", "indicators": [indicator], "rows": rows}


def _employment(con) -> dict[str, Any]:
    names = {
        "work in dubai": "阿联酋:Google搜索热度(work in dubai)",
        "work in uae": "阿联酋:Google搜索热度(work in uae)",
    }
    rows = _long_to_wide(
        con.execute("SELECT month, keyword, value FROM employment_search_index").fetchall(),
        lambda keyword: names[keyword],
    )
    return {"name": EMPLOYMENT_SHEET, "title": "Google Trends 阿联酋工作搜索热度", "indicators": list(names.values()), "rows": rows}


def _comtrade(con) -> dict[str, Any]:
    categories = {
        "manufacturing_equipment": "制造业设备",
        "civil_construction_equipment": "土木及基建施工设备",
        "energy_project_equipment": "能源项目设备",
        "drilling_equipment": "钻探设备",
        "port_rail_equipment": "港口及铁路专项设备",
    }
    indicators = [
        *[f"阿联酋:进口:{name}:当月值" for name in categories.values()],
        *[f"阿联酋:进口:{name}:台数:当月值" for name in categories.values()],
    ]
    periods: dict[date, dict[str, Any]] = defaultdict(dict)
    for period, category, value, units in con.execute(
        "SELECT period, category, value, units FROM comtrade_monthly"
    ).fetchall():
        name = categories[category]
        periods[period][f"阿联酋:进口:{name}:当月值"] = (
            float(value) / 1_000_000 if value is not None else None
        )
        periods[period][f"阿联酋:进口:{name}:台数:当月值"] = units
    return {"name": COMTRADE_SHEET, "title": "UN Comtrade 阿联酋资本品进口月度指标", "indicators": indicators, "rows": list(periods.items())}


def _vehicles(con) -> dict[str, Any]:
    indicators = [
        "阿联酋:进口:车辆(HS87)总量:当月值", "阿联酋:进口:乘用车:当月值",
        "阿联酋:进口:客车及巴士:当月值", "阿联酋:进口:货车:当月值",
        "阿联酋:进口:车辆零件:当月值", "阿联酋:乘用车进口量:当月值",
        "阿联酋:商用车进口量:当月值",
    ]
    periods: dict[date, dict[str, Any]] = defaultdict(dict)
    for period, code, value_usd, units in con.execute(
        "SELECT period, code, value_usd, units FROM comtrade_vehicles_monthly"
    ).fetchall():
        amount_names = {
            "87": "阿联酋:进口:车辆(HS87)总量:当月值",
            "8703": "阿联酋:进口:乘用车:当月值",
            "8702": "阿联酋:进口:客车及巴士:当月值",
            "8704": "阿联酋:进口:货车:当月值",
            "8708": "阿联酋:进口:车辆零件:当月值",
        }
        if code in amount_names:
            periods[period][amount_names[code]] = value_usd
        if code == "8703" and units is not None:
            periods[period]["阿联酋:乘用车进口量:当月值"] = units
        if code in {"8702", "8704"} and units is not None:
            name = "阿联酋:商用车进口量:当月值"
            periods[period][name] = periods[period].get(name, 0) + units
    return {"name": VEHICLES_SHEET, "title": "UN Comtrade HS87 阿联酋汽车进口月度指标", "indicators": indicators, "rows": list(periods.items())}


def _ded(con) -> dict[str, Any]:
    series_names = {
        "records": "迪拜:DED:当月快照记录数",
        "enterprises": "迪拜:当月有发证活动的企业数(企业号筛重)",
        "licences": "迪拜:当月新发执照数(执照号筛重)",
        "official_new_licenses": "迪拜:新发执照数(官方口径)",
    }
    rows = _long_to_wide(
        con.execute("SELECT month, series, value FROM ded_monthly").fetchall(),
        lambda series: series_names[series],
        period_transform=_month_end,
    )
    return {"name": DED_SHEET, "title": "DED 迪拜商业注册月度指标", "indicators": list(series_names.values()), "rows": rows}


def _foreign_labour(con) -> dict[str, Any]:
    series_names = {
        "philippines_total": "菲律宾_DMW部署_总计",
        "philippines_new_hires": "菲律宾_DMW部署_新雇",
        "philippines_rehires": "菲律宾_DMW部署_再雇",
        "nepal_with_reentry": "尼泊尔_DoFE批准_含再入境",
        "nepal_without_reentry": "尼泊尔_DoFE批准_不含再入境",
        "bangladesh_clearance": "孟加拉国_BMET出境许可",
        "proxy_sum": "重点三国合计_可比月",
        "proxy_index": "阿联酋:外籍劳动力:三国综合代理指数",
        "source_count": "阿联酋:外籍劳动力:来源覆盖数",
    }
    rows = _long_to_wide(
        con.execute(
            "SELECT period, series, value FROM foreign_labour_monthly "
            "WHERE series <> 'quality_flag'"
        ).fetchall(),
        lambda series: series_names[series],
    )
    return {"name": FOREIGN_LABOUR_SHEET, "title": "各国官方外籍劳动力月度指标", "indicators": list(series_names.values()), "rows": rows}


def _long_to_wide(records, name_builder, period_transform=lambda value: value):
    periods: dict[date, dict[str, Any]] = defaultdict(dict)
    for record in records:
        period = period_transform(record[0])
        name = name_builder(*record[1:-1]) if len(record) > 3 else name_builder(record[1])
        periods[period][name] = record[-1]
    return list(periods.items())


def merge(workbook_path: Path) -> dict[str, Any]:
    con = db.connect(read_only=True)
    try:
        raw_specs = [
            _eurostat(con), _dot(con), _dubai_customs(con), _salik(con),
            _employment(con), _comtrade(con), _vehicles(con), _ded(con),
            _foreign_labour(con),
        ]
        for spec in raw_specs:
            spec["metadata"] = _metadata(con, spec["indicators"])
        counts = write_indicator_sheets(workbook_path, raw_specs)
    finally:
        con.close()
    return {
        "status": "ok",
        "note": "；".join(f"{name} {count} 行" for name, count in counts.items()),
    }


if __name__ == "__main__":
    print(merge(DATA_DIR / "阿联酋.xlsx"))
