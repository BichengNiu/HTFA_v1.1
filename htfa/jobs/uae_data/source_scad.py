"""SCAD 阿布扎比酒店统计与酒店价格指数：月度入库与写表。

数据来源：Statistics Centre – Abu Dhabi（SCAD，官网 statad.gov.ae）每月发布的
月度快照 Excel（``data/UAE/raw/scad/hotel/``）：

- ``HotelStats_YYYY-MM.xlsx``：**Hotel Statistics / Hotel Establishments
  Statistics**，Table 1 关键指标（酒店家数、房间数、客人数、客夜数、平均入住时长、
  入住率、平均房价 ADR、RevPAR）。
- ``HPI_YYYY-MM.xlsx``：**Hotel Price Index**，Table 1 的 `Hotel Price Index`
  行（加权平均指数）。

每个文件只含「当月 / 上月 / 去年同月」三列快照，没有全历史序列，故本模块
解析后按 (period, indicator) 入长表 ``scad_monthly`` 自建连续月度序列。

口径注意（已在 raw/scad/README.md 记录）：

- HS 2023-08/09/10 的入住率单元格为 0–100 百分数（如 72），2024 起为 0–1 比例，
  写表时统一换算为百分比（×100）保证列内量纲一致。
- 2023-04/07 旧格式缺「平均房价 ADR」列（avg_room_rate_aed 为 None，仅 2024 起
  有值）。
- HPI 2023-06、2023-08 官网未发布月度文件（官方缺期，不插值、不存行）。
- HS 2023 年仅 4、7–11 月有官方文件（官方缺期，不存行）。
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    run_powershell_sheet_writer,
)

RAW_DIR = DATA_DIR / "raw" / "scad" / "hotel"
TARGET_SHEET = "月度_SCAD"
DICTIONARY_SHEET = "指标字典"
SOURCE_NAME = "SCAD"
INDUSTRY = "住宿/旅游"

# HS Table 1 关键指标：(指标名, 子串前缀, 频率, 单位)
HS_INDICATORS = (
    ("阿布扎比:酒店家数(家)", "Number of hotel establ", "月", "家"),
    ("阿布扎比:酒店房间数(间)", "Number of rooms", "月", "间"),
    ("阿布扎比:酒店客人数(千人)", "Number of guests", "月", "千人"),
    ("阿布扎比:酒店客夜数(千夜)", "Number of guest nights", "月", "千夜"),
    ("阿布扎比:酒店平均入住时长(夜)", "Average length of stay", "月", "夜"),
    ("阿布扎比:酒店入住率(%)", "Occupancy rate", "月", "%"),
    ("阿布扎比:酒店平均房价(迪拉姆/夜)", "Average room rate", "月", "迪拉姆/夜"),
    ("阿布扎比:酒店RevPAR(迪拉姆)", "Revenue per available", "月", "迪拉姆/夜"),
)

# HPI Table 1 的 `Hotel Price Index` 行（当月第一列）
HPI_INDICATORS = (
    ("阿布扎比:酒店价格指数(HPI)", "Hotel Price Index", "月", "指数"),
)

_INDICATOR_KEY = {row[0]: row for row in HS_INDICATORS + HPI_INDICATORS}
_INDICATOR_ORDER = {
    name: index for index, (name, *_) in enumerate(HS_INDICATORS + HPI_INDICATORS)
}

_SERIES_SLUG = {
    "HotelStats": "HS",
    "HPI": "HPI",
}

_FILE_PERIOD = re.compile(r"(20\d{2})-(0[1-9]|1[0-2])\.xlsx")


def _month_end(year: int, month: int) -> date:
    year_next = year + (month == 12)
    month_next = 1 if month == 12 else month + 1
    first = date(year_next, month_next, 1)
    return date.fromordinal(first.toordinal() - 1)


def parse_hotel_stats_rows(rows: list) -> dict[str, float | None]:
    """从 HS 工作簿 Table 1 提取当月关键指标。

    Table 1 结构：标签在 B 列（旧格式 A/B 有 Series ID 偏移），数值为第一个可转
    浮点的单元格。入住率统一换算为百分比（0–1 概率值 ×100，百分数原样保留）。
    """

    wanted: list[tuple[str, str]] = [(name, prefix) for name, prefix, *_ in HS_INDICATORS]
    result: dict[str, float | None] = {}
    for row in rows:
        cells = [str(c).strip() if c is not None else "" for c in row]
        for name, prefix in wanted:
            if name in result:
                continue
            for i, cell in enumerate(cells):
                if cell.startswith(prefix):
                    number = _first_number(cells[i + 1:])
                    if number is None:
                        result[name] = None
                    elif name.endswith("入住率(%)"):
                        result[name] = number * 100 if 0.0 < number <= 1.0 else number
                    else:
                        result[name] = number
                    break
    return result


def parse_hpi_rows(rows: list) -> dict[str, float | None]:
    """从 HPI 工作簿 Table 1 提取当月 `Hotel Price Index` 行数值。"""

    for row in rows:
        cells = [str(c).strip() if c is not None else "" for c in row]
        for i, cell in enumerate(cells):
            if cell == "Hotel Price Index" or cell.startswith("Hotel Price Index"):
                number = _first_number(cells[i + 1:])
                return {"阿布扎比:酒店价格指数(HPI)": number}
    return {}


def _first_number(cells: Iterable[str]) -> float | None:
    for cell in cells:
        try:
            return float(cell.replace(",", ""))
        except ValueError:
            continue
    return None


def _parse_workbook(path: Path) -> dict[str, float | None]:
    match = _FILE_PERIOD.search(path.name)
    if match is None:
        raise ValueError(f"Unexpected hotel filename (expected YYYY-MM.xlsx): {path.name}")
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        table1 = workbook["Table 1"]
        rows = list(table1.iter_rows(values_only=True))
    finally:
        workbook.close()
    if path.name.upper().startswith("HPI"):
        return parse_hpi_rows(rows)
    if path.name.upper().startswith("HOTELSTATS"):
        return parse_hotel_stats_rows(rows)
    raise ValueError(f"Unexpected hotel series prefix: {path.name}")


def _long_rows(paths: Iterable[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(paths):
        year, month = _FILE_PERIOD.search(path.name).groups()
        period = _month_end(int(year), int(month))
        try:
            parsed = _parse_workbook(path)
        except (OSError, ValueError) as exc:
            # 单文件解析失败只记录该文件，不中断整体（与 cbuae 风格一致）
            rows.append(
                {
                    "period": period,
                    "indicator": "__parse_error__",
                    "value": None,
                    "source_file": f"{path.name}: {exc}",
                }
            )
            continue
        for name, value in parsed.items():
            if value is None:
                continue
            rows.append(
                {
                    "period": period,
                    "indicator": name,
                    "value": value,
                    "source_file": path.name,
                }
            )
    return rows


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": name,
            "frequency": frequency,
            "unit": unit,
            "source": SOURCE_NAME,
            "type": "指标",
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name, _prefix, frequency, unit in HS_INDICATORS + HPI_INDICATORS
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """扫描 raw/scad/hotel/ 下月度 Excel → 入长表 scad_monthly + 指标字典。

    本数据源无网络下载环节（文件来自官网手工下载），``skip_download``/``force``
    仅作签名兼容。
    """

    paths = [
        path
        for path in RAW_DIR.glob("*.xlsx")
        if path.stem.startswith(("HotelStats", "HPI"))
        and _FILE_PERIOD.search(path.name)
    ]
    rows = _long_rows(paths)
    # 剔除解析错误占位行
    error_rows = [row for row in rows if row["indicator"] == "__parse_error__"]
    rows = [row for row in rows if row["indicator"] != "__parse_error__"]

    con.execute("DELETE FROM scad_monthly")
    if rows:
        con.executemany(
            "INSERT INTO scad_monthly (period, indicator, value, source_file) "
            "VALUES (?, ?, ?, ?)",
            [(row["period"], row["indicator"], row["value"], row["source_file"]) for row in rows],
        )
    db.upsert_dictionary_rows(con, _dictionary_rows())

    periods = sorted({row["period"] for row in rows})
    indicators = sorted({row["indicator"] for row in rows})
    note = f"{len(periods)} 个月 × {len(indicators)} 指标"
    if error_rows:
        note += f"；{len(error_rows)} 文件解析失败（{error_rows[0]['source_file']}）"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """把 scad_monthly 写回 阿联酋.xlsx 的 月度_SCAD sheet。

    每次调用重建该 sheet：数据来自库中长表，按 HS_INDICATORS+HPI_INDICATORS 顺序
    还原宽表记录，最新在前；缺失月份/指标单元格留空（官方缺期不插值）。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_scad_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, indicator, value FROM scad_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()

    indicators = [name for name, *_ in HS_INDICATORS + HPI_INDICATORS]
    by_period: dict[str, list] = {}
    for period, indicator, value in db_rows:
        key = period.strftime("%Y-%m")
        if key not in by_period:
            by_period[key] = [None] * len(indicators)
        by_period[key][_INDICATOR_ORDER[indicator]] = float(value)

    observations = sorted(
        (
            {"period": key, "values": values}
            for key, values in by_period.items()
        ),
        key=lambda item: item["period"],
    )
    if not observations:
        raise ValueError("scad_monthly is empty; nothing to merge")

    payload = {
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月",
        "unit": "",
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": "指标", "industry": INDUSTRY, "unit": unit}
            for name, _prefix, _frequency, unit in HS_INDICATORS + HPI_INDICATORS
        ],
        "records": [
            {
                "period": item["period"],
                "values": [None if v is None else float(v) for v in item["values"]],
            }
            for item in observations[::-1]
        ],
    }
    with payload_json_file(
        payload,
        prefix=".scad-sheet-",
        directory=DATA_DIR,
    ) as payload_path:
        run_powershell_sheet_writer(
            helper_path, workbook_path, payload_path, TARGET_SHEET
        )
    return {
        "status": "ok",
        "note": f"{len(observations)} 个月写入 {TARGET_SHEET}",
    }


if __name__ == "__main__":
    print("source_scad.py 自检：")
    print("  update(con, force=, skip_download=) 解析 raw/scad/hotel/ 并入 scad_monthly")
    print("  merge(workbook_path) 把表写回 月度_SCAD")
    print("  本文件直接运行不执行任何下载或工作簿写入。")
