"""CBUAE 政府/政府控股企业存贷款月度入库与写表。

逻辑移植自 ``scripts/data_sources/cbuae/update_cbuae_monthly.py``：扫描
``data/UAE/raw/cbuae/`` 下全部 YYYY-MM.xlsx / YYYY-MM.pdf 统计公报，读取全银行口径的
国内信贷与居民/非居民存款两张表，为每个观测月保留最新 vintage；无工作簿的月份
回退解析 PDF；仍缺的月份用 ``data/UAE/阿联酋.xlsx`` 的 月度_Wind sheet 回填（只读）。
入库为长表 ``cbuae_monthly``（(period, indicator) 一行），单位百万迪拉姆。
"""

from __future__ import annotations

import calendar
import re
import sys
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Iterator

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from pypdf import PdfReader

DATA_DIR = Path(__file__).resolve().parent
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

import db  # noqa: E402
from _excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)

# ---------------------------------------------------------------------------
# 常量（与旧脚本一致）
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "cbuae"
WIND_PATH = DATA_DIR / "阿联酋.xlsx"
TARGET_SHEET = "月度_CBUAE"
DICTIONARY_SHEET = "指标字典"
SOURCE_NAME = "CBUAE"
UNIT = "百万迪拉姆"
INDUSTRY = "金融"
START_PERIOD = "2019-12"

MONTH_NUMBERS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

PERIOD_PATTERN = re.compile(
    r"\b(" + "|".join(MONTH_NUMBERS) + r")[a-z]*\s+(20\d{2})\b",
    re.IGNORECASE,
)
FILE_PERIOD_PATTERN = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")
NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

CBUAE_INDICATORS = (
    ("阿联酋政府存款", "存款"),
    ("阿联酋政府控股企业存款", "存款"),
    ("阿联酋政府信贷", "信贷"),
    ("阿联酋政府控股企业信贷", "信贷"),
)
INDICATOR_ORDER = {name: index for index, (name, _) in enumerate(CBUAE_INDICATORS)}

WIND_FALLBACK_INDICATORS = (
    "阿联酋:银行存款:居民存款:政府部门",
    "阿联酋:银行存款:居民存款:政府相关实体(政府持股超50%)",
    "阿联酋:信贷总额:国内信贷:政府部门",
    "阿联酋:信贷总额:国内信贷:公共部门(政府相关实体)",
)

CBUAE_PRIMARY_START = "2020-01"


@dataclass(frozen=True)
class Observation:
    """一个观测期的一个来源 vintage。"""

    period: str
    values: tuple[Decimal, Decimal, Decimal, Decimal]
    source_period: str
    source_file: str


def _normalize_label(value: object) -> str:
    """规范化表标签且不改变其语义内容。"""

    if not isinstance(value, str):
        return ""
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\*+", "", value)
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return re.sub(r"\(\s*([^)]*?)\s*\)", r"(\1)", value)


def _parse_period(value: object) -> str | None:
    """解析公报中的英文月份表头，返回 YYYY-MM。"""

    if not isinstance(value, str):
        return None
    match = PERIOD_PATTERN.search(value)
    if not match:
        return None
    month = MONTH_NUMBERS[match.group(1).casefold()]
    return f"{match.group(2)}-{month:02d}"


def _source_period(path: Path) -> str:
    """从规范化 YYYY-MM 文件名读取公报期间。"""

    if not FILE_PERIOD_PATTERN.fullmatch(path.stem):
        raise ValueError(f"Unexpected bulletin filename: {path.name}")
    return path.stem


def _to_decimal(value: object) -> Decimal | None:
    """把 Excel 数值单元格转换为稳定的三位小数。"""

    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    return number.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _sheet_text(sheet: Worksheet, max_rows: int = 10) -> str:
    """返回报表标题/表头区的规范化文本。"""

    values: list[str] = []
    for row in sheet.iter_rows(min_row=1, max_row=min(max_rows, sheet.max_row)):
        values.extend(str(cell.value) for cell in row if cell.value is not None)
    return _normalize_label(" ".join(values))


def _find_source_sheets(workbook: object) -> tuple[Worksheet, Worksheet]:
    """定位全银行口径的国内信贷与存款工作表。"""

    credit_sheet: Worksheet | None = None
    deposit_sheet: Worksheet | None = None
    for sheet in workbook.worksheets:
        text = _sheet_text(sheet)
        if "domestic credit" in text and "all banks" in text:
            credit_sheet = sheet
        if (
            "deposits distributed residents / non residents" in text
            and "all banks" in text
        ):
            deposit_sheet = sheet
    if credit_sheet is None or deposit_sheet is None:
        raise ValueError("Required all-banks credit/deposit worksheets not found")
    return credit_sheet, deposit_sheet


def _header_columns(sheet: Worksheet) -> dict[str, int]:
    """把观测期映射到工作表列号。"""

    columns: dict[str, int] = {}
    for row in sheet.iter_rows(min_row=1, max_row=min(12, sheet.max_row)):
        for cell in row:
            period = _parse_period(cell.value)
            if period:
                columns[period] = cell.column
    if not columns:
        raise ValueError(f"No English month headers found in {sheet.title}")
    return columns


def _find_row(sheet: Worksheet, accepted_labels: set[str]) -> int:
    """查找包含规范化标签中某一行的行号。"""

    for row_number, row in enumerate(sheet.iter_rows(), start=1):
        if any(_normalize_label(cell.value) in accepted_labels for cell in row):
            return row_number
    labels = ", ".join(sorted(accepted_labels))
    raise ValueError(f"Labels not found in {sheet.title}: {labels}")


def _extract_sheet_rows(
    sheet: Worksheet,
    label_sets: tuple[set[str], set[str]],
) -> dict[str, tuple[Decimal, Decimal]]:
    """提取一个工作表中每个日期列的两个指标行。"""

    columns = _header_columns(sheet)
    first_row = _find_row(sheet, label_sets[0])
    second_row = _find_row(sheet, label_sets[1])
    extracted: dict[str, tuple[Decimal, Decimal]] = {}
    for period, column in columns.items():
        first = _to_decimal(sheet.cell(first_row, column).value)
        second = _to_decimal(sheet.cell(second_row, column).value)
        if first is not None and second is not None:
            extracted[period] = (first, second)
    return extracted


def extract_workbook(path: Path) -> list[Observation]:
    """从一个工作簿提取所有完整的期间观测。"""

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        credit_sheet, deposit_sheet = _find_source_sheets(workbook)
        deposits = _extract_sheet_rows(
            deposit_sheet,
            ({"government"}, {"gres"}),
        )
        credits = _extract_sheet_rows(
            credit_sheet,
            ({"government"}, {"public sector", "public sector (gres)"}),
        )
    finally:
        workbook.close()

    source_period = _source_period(path)
    observations: list[Observation] = []
    for period in sorted(deposits.keys() & credits.keys()):
        government_deposits, gre_deposits = deposits[period]
        government_credit, gre_credit = credits[period]
        observations.append(
            Observation(
                period=period,
                values=(
                    government_deposits,
                    gre_deposits,
                    government_credit,
                    gre_credit,
                ),
                source_period=source_period,
                source_file=path.name,
            )
        )
    return observations


def _last_number(line: str) -> Decimal | None:
    """返回一行提取的 PDF 表格数据中的最后一个数值记号。"""

    matches = NUMBER_PATTERN.findall(line)
    if not matches:
        return None
    return _to_decimal(matches[-1])


def extract_pdf_fallback(path: Path) -> Observation:
    """从仅 PDF 公报中提取公报月数值。"""

    deposit_values: tuple[Decimal, Decimal] | None = None
    credit_values: tuple[Decimal, Decimal] | None = None
    reader = PdfReader(path)

    for page in reader.pages:
        text = page.extract_text() or ""
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        if "Table 23 : Domestic Credit" in text or "Domestic Credit ( All Banks )" in text:
            government = next(
                (_last_number(line) for line in lines if re.match(r"^Government\s", line)),
                None,
            )
            public_sector = next(
                (_last_number(line) for line in lines if re.match(r"^Public Sector(?:\s|$)", line)),
                None,
            )
            if government is not None and public_sector is not None:
                credit_values = (government, public_sector)

        if (
            "Deposits distributed Residents / Non Residents ( All Banks )"
            in text
        ):
            government = next(
                (_last_number(line) for line in lines if re.match(r"^1\.3 Government\s", line)),
                None,
            )
            gres = next(
                (_last_number(line) for line in lines if re.match(r"^1\.4 GREs\s", line)),
                None,
            )
            if government is not None and gres is not None:
                deposit_values = (government, gres)

    if deposit_values is None or credit_values is None:
        raise ValueError(f"Required PDF tables could not be parsed: {path.name}")

    period = _source_period(path)
    return Observation(
        period=period,
        values=(*deposit_values, *credit_values),
        source_period=period,
        source_file=path.name,
    )


def extract_wind_fallback(path: Path) -> list[Observation]:
    """读取四条匹配的 Wind 序列并把十亿换算为百万。"""

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = (
            workbook["月度_Wind"]
            if "月度_Wind" in workbook.sheetnames
            else workbook.active
        )
        expected_names = {
            _normalize_label(name): name for name in WIND_FALLBACK_INDICATORS
        }
        matching_columns: dict[str, int] = {}
        header_row = next(
            sheet.iter_rows(min_row=2, max_row=2, values_only=True)
        )
        for column, value in enumerate(header_row[1:], start=2):
            normalized_name = _normalize_label(value)
            if normalized_name not in expected_names:
                continue
            if normalized_name in matching_columns:
                raise ValueError(
                    "Duplicate Wind fallback indicator: "
                    + expected_names[normalized_name]
                )
            matching_columns[normalized_name] = column

        missing = [
            name
            for name in WIND_FALLBACK_INDICATORS
            if _normalize_label(name) not in matching_columns
        ]
        if missing:
            raise ValueError(
                "Missing Wind fallback indicators: " + ", ".join(missing)
            )

        ordered_columns = [
            matching_columns[_normalize_label(name)]
            for name in WIND_FALLBACK_INDICATORS
        ]
        unit_row = next(
            sheet.iter_rows(min_row=4, max_row=4, values_only=True)
        )
        units = [
            _normalize_label(unit_row[column - 1])
            for column in ordered_columns
        ]
        if any(unit != _normalize_label("十亿阿联酋迪拉姆") for unit in units):
            raise ValueError("Wind indicators are not in billions of AED")

        observations: list[Observation] = []
        for row in sheet.iter_rows(min_row=7, values_only=True):
            period_value = row[0]
            if not isinstance(period_value, (date, datetime)):
                continue
            converted = tuple(
                _to_decimal(Decimal(str(value)) * Decimal("1000"))
                for value in (row[column - 1] for column in ordered_columns)
            )
            if any(value is None for value in converted):
                continue
            period = period_value.strftime("%Y-%m")
            observations.append(
                Observation(
                    period=period,
                    values=converted,
                    source_period=period,
                    source_file=path.name,
                )
            )
        return observations
    finally:
        workbook.close()


def _iter_months(start: str, end: str) -> Iterable[str]:
    """产出包含起止月份的连续 YYYY-MM 期间。"""

    current = datetime.strptime(start, "%Y-%m")
    final = datetime.strptime(end, "%Y-%m")
    while current <= final:
        yield current.strftime("%Y-%m")
        year = current.year + (current.month == 12)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)


def select_latest_vintages(
    observations: Iterable[Observation],
    start_period: str,
    end_period: str | None,
) -> tuple[list[Observation], list[str], int]:
    """为每个期间选择最新 vintage 并报告修订情况。"""

    by_period: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        if observation.period >= start_period:
            by_period[observation.period].append(observation)

    if not by_period:
        raise ValueError("No observations were extracted")
    effective_end = end_period or max(by_period)
    selected: list[Observation] = []
    revised_periods = 0
    for period, candidates in sorted(by_period.items()):
        if period > effective_end:
            continue
        if len({candidate.values for candidate in candidates}) > 1:
            revised_periods += 1
        selected.append(max(candidates, key=lambda item: (item.source_period, item.source_file)))

    available = {observation.period for observation in selected}
    missing = [
        period
        for period in _iter_months(start_period, effective_end)
        if period not in available
    ]
    return selected, missing, revised_periods


def add_missing_fallbacks(
    primary: Iterable[Observation],
    fallback: Iterable[Observation],
    start_period: str,
    end_period: str | None,
) -> tuple[list[Observation], list[str]]:
    """仅在主序列缺期间的位置补充回填观测。"""

    merged = {observation.period: observation for observation in primary}
    added: list[str] = []
    for observation in fallback:
        if observation.period < start_period:
            continue
        if end_period is not None and observation.period > end_period:
            continue
        if observation.period not in merged:
            merged[observation.period] = observation
            added.append(observation.period)
    return [merged[period] for period in sorted(merged)], sorted(added)


def _month_end(period: str) -> date:
    """'YYYY-MM' -> 该月最后一天的 date。"""

    year, month = (int(part) for part in period.split("-"))
    return date(year, month, calendar.monthrange(year, month)[1])


@contextmanager
def _transaction(con) -> Iterator[None]:
    """事务上下文：duckdb 1.5.5 的 `with con.begin():` 退出时会把连接一并
    关闭（begin 返回的是子连接），因此手动管理提交/回滚。"""

    transaction = con.begin()
    try:
        yield
    except BaseException:
        transaction.rollback()
        raise
    else:
        transaction.commit()


def _long_rows(observations: Iterable[Observation]) -> list[dict]:
    """把宽表观测展开为 (period, indicator) 长表入库行。"""

    rows: list[dict] = []
    for observation in observations:
        for (indicator, _), value in zip(CBUAE_INDICATORS, observation.values):
            rows.append(
                {
                    "period": _month_end(observation.period),
                    "indicator": indicator,
                    "value": value,
                    "source_period": observation.source_period,
                    "source_file": observation.source_file,
                }
            )
    return rows


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": name,
            "frequency": "月",
            "unit": UNIT,
            "source": SOURCE_NAME,
            "type": indicator_type,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name, indicator_type in CBUAE_INDICATORS
    ]


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """发现公报文件 -> 解析（xlsx 优先，pdf 回退）-> vintage 选择 -> 入库。

    本数据源无网络下载环节（公报由外部环节放入 data/UAE/raw/cbuae/），因此
    ``skip_download``/``force`` 仅作签名兼容。Wind 回填只读 data/UAE/阿联酋.xlsx，
    绝不写入该文件。
    """

    observations: list[Observation] = []
    errors: list[str] = []
    workbook_paths = sorted(RAW_DIR.glob("20??-??.xlsx"))
    for path in workbook_paths:
        try:
            observations.extend(extract_workbook(path))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")

    workbook_periods = {path.stem for path in workbook_paths}
    for path in sorted(RAW_DIR.glob("20??-??.pdf")):
        if path.stem in workbook_periods:
            continue
        try:
            observations.append(extract_pdf_fallback(path))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")

    primary_start = max(START_PERIOD, CBUAE_PRIMARY_START)
    selected, _, revised_periods = select_latest_vintages(
        observations,
        start_period=primary_start,
        end_period=None,
    )
    fallback_added: list[str] = []
    if WIND_PATH.is_file():
        try:
            selected, fallback_added = add_missing_fallbacks(
                selected,
                extract_wind_fallback(WIND_PATH),
                start_period=START_PERIOD,
                end_period=None,
            )
        except (OSError, ValueError) as exc:
            errors.append(f"{WIND_PATH.name}: {exc}")
    else:
        errors.append(f"{WIND_PATH.name}: Wind fallback file not found")

    rows = _long_rows(selected)
    with _transaction(con):
        db.replace(con, "cbuae_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"{len(selected)} 个观察月（{selected[0].period} 至 {selected[-1].period}）"
        f"× {len(CBUAE_INDICATORS)} 指标；vintage 修订 {revised_periods} 期；"
        f"Wind 回填 {len(fallback_added)} 期"
    )
    if errors:
        note += f"；源警告 {len(errors)} 条，首条：{errors[0]}"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """把 cbuae_monthly 写回 阿联酋.xlsx 的 月度_CBUAE sheet。

    与旧脚本一致：每次调用都重建该 sheet（无幂等检查），数据来自库中长表，
    按 CBUAE_INDICATORS 顺序还原宽表记录，最新在前。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_cbuae_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, indicator, value, source_period, source_file "
            "FROM cbuae_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()

    by_period: dict[str, dict] = {}
    for period, indicator, value, source_period, source_file in db_rows:
        key = period.strftime("%Y-%m")
        item = by_period.setdefault(
            key,
            {"values": [None] * len(CBUAE_INDICATORS),
             "source_period": source_period,
             "source_file": source_file},
        )
        item["values"][INDICATOR_ORDER[indicator]] = value
    observations = [
        Observation(
            period=period,
            values=tuple(item["values"]),
            source_period=item["source_period"],
            source_file=item["source_file"],
        )
        for period, item in sorted(by_period.items())
    ]
    if not observations:
        raise ValueError("cbuae_monthly is empty; nothing to merge")
    if any(value is None for observation in observations for value in observation.values):
        raise ValueError("cbuae_monthly 中某期间缺少指标列，无法还原宽表")

    payload = {
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月",
        "unit": UNIT,
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": indicator_type, "industry": INDUSTRY}
            for name, indicator_type in CBUAE_INDICATORS
        ],
        "records": records_latest_first(observations),
    }
    with payload_json_file(
        payload,
        prefix=".cbuae-sheet-",
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
    print("source_cbuae.py 自检：")
    print("  update(con, force=, skip_download=) 解析 data/UAE/raw/cbuae/ 下公报")
    print("    （xlsx 优先、pdf 回退、Wind 补缺）并入库 cbuae_monthly 长表")
    print("  merge(workbook_path) 把表写回 月度_CBUAE")
    print("  本文件直接运行不执行任何下载或工作簿写入。")