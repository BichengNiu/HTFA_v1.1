"""Original annual volumes, not copied daily estimates. Reviewed 2026-09-30.

Iraq EITI 2021 printed pp.133-134, tables 57 (NOC) / 58 (PCLD).
Keep the company basis: their conflicting Qayyarah returns are not reconciled.
Calendar-day means are historical estimates, never present-day production.
"""

from calendar import isleap
from decimal import Decimal, ROUND_HALF_UP

EITI_2021_URL = "https://eiti.org/sites/default/files/2024-01/Iraq%202021%20EITI%20Report.pdf"
EITI_2016_URL = "https://eiti.org/sites/default/files/attachments/iraq_2016_eiti_report.pdf"
EITI_2023_URL = "https://eiti.org/sites/default/files/Iraq%202023%20EITI%20Report.docx"

# field, reporting year, annual barrels, source table, company return
ANNUAL_VOLUMES = (
    ("Bai Hassan", 2021, 48672087, "57", "NOC"),
    ("Baba Dome", 2021, 26822678, "57", "NOC"),
    ("Avana Dome", 2021, 12542338, "57", "NOC"),
    ("Jambur", 2021, 14008692, "57", "NOC"),
    ("Khabbaz", 2021, 9139429, "57", "NOC"),
    ("Ajil", 2021, 2167278, "57", "NOC"),
    ("Ain Zalah", 2021, 1412999, "57", "NOC"),
    ("Batmah", 2021, 247597, "57", "NOC"),
    ("West Qurna-2", 2021, 146022515, "58", "PCLD"),
    ("Zubair", 2021, 171760022, "58", "PCLD"),
    ("Majnoon", 2021, 64240000, "58", "PCLD"),
    ("Halfaya", 2021, 142213694, "58", "PCLD"),
    ("Missan Fields", 2021, 80650634, "58", "PCLD"),
    ("Badra", 2021, 12857981, "58", "PCLD"),
    ("Ahdab", 2021, 17956867, "58", "PCLD"),
    ("East Baghdad", 2021, 6630000, "58", "PCLD"),
    ("Luhais", 2016, 32631608, "p.75", "Basra Oil Company"),
    ("Tuba", 2016, 13262897, "p.75", "Basra Oil Company"),
    ("Artawi", 2016, 6123726, "p.75", "Basra Oil Company"),
)

# Same original slide (QatarEnergy November 2025, slide 12), different commodity.
# Do not add natural gas to oil barrels or use BOE conversion without a convention.
QATAR_GAS_2024_MMSCFD = {
    "Dukhan": "229.0", "Maydan Mahzam": "28.6", "Bul Hanine": "38.6",
    "Idd El-Sharqi": "39.9", "Al-Rayyan": "0.3", "Al Shaheen": "198.7",
    "Al-Khaleej": "4.4",
}


def additional_measurements(assets: list[dict]) -> None:
    for asset in assets:
        asset["additional_measurements"] = []
        if asset["country"] == "卡塔尔" and asset["name"] in QATAR_GAS_2024_MMSCFD:
            asset["additional_measurements"].append(dict(
                value=QATAR_GAS_2024_MMSCFD[asset["name"]], unit="百万标准立方英尺/日",
                metric_type="actual_output", commodity="natural_gas", data_date="2024年平均",
                basis="QatarEnergy 2025-11投资者演示第12页原表；历史全资产口径",
                source_url=asset["source_url"]))
        if asset["name"] == "Bahrain Field (Awali)":
            asset["additional_measurements"].append(dict(
                value="1,647", unit="百万标准立方英尺/日", metric_type="actual_output",
                commodity="natural_gas", data_date="2022年平均",
                basis="Bahrain BTR1原报告同一段；不可与原油/凝析油相加",
                source_url="https://unfccc.int/sites/default/files/resource/30112025_Bahrain%27s_BTR1_2024_to_the_UNFCCC_vSubmitted.pdf"))
        if asset["name"] == "Ghasha Concession":
            asset["additional_measurements"].append(dict(
                value="1,800", unit="百万标准立方英尺/日", metric_type="target_capacity",
                commodity="natural_gas", data_date="2025-11-24公告目标",
                basis="目标，不是当期实产；整个特许区，不拆给组成田",
                source_url=asset["source_url"]))
        if asset["name"] == "Qayyarah":
            asset["conflicting_annual_returns"] = [
                {"company": "NOC", "annual_barrels": 1821143, "year": 2021, "table": "57"},
                {"company": "PCLD", "annual_barrels": 1775463, "year": 2021, "table": "58"},
            ]


def daily_thousand_barrels(annual_barrels: int, year: int) -> str:
    days = 366 if isleap(year) else 365
    return str((Decimal(annual_barrels) / days / 1000).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP))


def apply_annual_volumes(assets: list[dict]) -> None:
    index = {(a["country"], a["name"]): a for a in assets}
    for name, year, barrels, table, company in ANNUAL_VOLUMES:
        asset = index[("伊拉克", name)]
        days = 366 if isleap(year) else 365
        asset.update(value=daily_thousand_barrels(barrels, year),
                     metric_type="derived_daily_average", unit="千桶/日",
                     data_date=f"{year}年历史日均（全年{days}日）",
                     source=f"Iraq EITI {year}",
                     source_url=EITI_2021_URL if year == 2021 else EITI_2016_URL,
                     annual_barrels=barrels, calendar_days=days,
                     measurement_basis=f"{company}年度报送；表{table}",
                     numeric_audit="原始年度量及日均公式已复核（历史）")
        asset["note"] = (f"EITI {year} {company}表{table}年产{barrels:,}桶÷{days}日÷1000，"
                         "四舍五入至0.1千桶/日；历史全年日均，不能解释为当前日产量。"
                         + ("此处为许可证南区报送范围，不能代表East Baghdad全部区域。"
                            if name == "East Baghdad" else "")
                         + ("三个组成田合计，不能拆给Fakkah、Bazerkan、Abu Gharb。"
                            if name == "Missan Fields" else ""))
