"""CBUAE 政府/政府控股企业存贷款与外资流向指标月度入库与写表。

逻辑移植自 ``scripts/data_sources/cbuae/update_cbuae_monthly.py``：扫描
``data/UAE/raw/cbuae/`` 下全部 YYYY-MM.xlsx / YYYY-MM.pdf 统计公报，读取全银行口径的
国内信贷、居民/非居民存款、按币种存款、国外资产负债等多张表，为每个观测月保留
最新 vintage；无工作簿的月份回退解析 PDF。入库为长表 ``cbuae_monthly``
（(period, indicator) 一行），单位百万迪拉姆。数据一律直接来自 CBUAE 公报，不依赖
任何 Wind 序列。

外资流向口径：非居民存款分项（个人/政府及非商业实体/其他金融企业）取自存款表
「非居民」块(2)；外币存款总额取自按币种存款表；银行国外资产/负债取自国外资产负债表
（All Banks）。均为月度存量，表征外资流入须结合环比增量解读，不含 FDI。

支付体系月度数据：同批 CBUAE 月度公报的 Cheques(ICCS) 与 FTS 两表（表 36/37 或
47/48）亦一并入库为 ``cbuae_monthly`` 的 8 个「支付」指标（金额百万迪拉姆、笔数
为张/笔），口径为公报原样发布的年内累计(YTD，每年 1 月重置)；单月增量需在分析层
差分。PDF 回退月（如 2020-01）不覆盖支付表。
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

CBUAE_CREDIT_INDICATORS = (
    ("阿联酋政府存款", "存款"),
    ("阿联酋政府控股企业存款", "存款"),
    ("阿联酋政府信贷", "信贷"),
    ("阿联酋政府控股企业信贷", "信贷"),
    ("阿联酋:国内信贷:私人企业信贷(Private Corporate Credit)", "信贷"),
    ("阿联酋:国内信贷:商业及工业部门信贷(Business & Industrial Sector Credit)", "信贷"),
    ("阿联酋:非居民存款:私人企业存款(Private Corporate Deposit)", "存款"),
    ("阿联酋:非居民存款:商业及工业部门存款(Business & Industrial Sector Deposit)", "存款"),
    ("阿联酋:非居民存款:个人存款(Individuals Deposit)", "存款"),
    ("阿联酋:非居民存款:政府及非商业实体存款(Government & Non Commercial Entities Deposit)", "存款"),
    ("阿联酋:非居民存款:其他金融企业存款(Other Financial Corporations Deposit)", "存款"),
    ("阿联酋:外币存款(Total Foreign Currencies)", "存款"),
    ("阿联酋:银行国外资产(Foreign Assets)", "资产"),
    ("阿联酋:银行国外负债(Foreign Liabilities)", "负债"),
    ("阿联酋:国内信贷:个人信贷(Individual Credit)", "信贷"),
)

# 支付体系逐月数据（来自公报表36/37 或 47/48）：
#   Cheques(ICCS)：SWIFT之外的国家动产清算，公报给年内累计(YTD)口径（每年1月重置）。
#   FTS：UAE Funds Transfer System 的逐月累计笔数与金额（金额单位为百万迪拉姆）。
CBUAE_PAYMENT_INDICATORS = (
    ("阿联酋:支票清算笔数(累计)Cheques Cleared Number", "支付"),
    ("阿联酋:支票清算金额(累计)Cheques Cleared Amount", "支付"),
    ("阿联酋:FTS客户转账笔数(累计)Customer Transfers Number", "支付"),
    ("阿联酋:FTS客户转账金额(累计)Customer Transfers Amount", "支付"),
    ("阿联酋:FTS银行转账笔数(累计)Bank Transfers Number", "支付"),
    ("阿联酋:FTS银行转账金额(累计)Bank Transfers Amount", "支付"),
    ("阿联酋:FTS国内资金转账总额笔数(累计)Total Fund Transfers Number", "支付"),
    ("阿联酋:FTS国内资金转账总额金额(累计)Total Fund Transfers Amount", "支付"),
)

CBUAE_INDICATORS = CBUAE_CREDIT_INDICATORS + CBUAE_PAYMENT_INDICATORS
INDICATOR_ORDER = {name: index for index, (name, _) in enumerate(CBUAE_INDICATORS)}
CREDIT_INDICATOR_COUNT = len(CBUAE_CREDIT_INDICATORS)

CBUAE_PRIMARY_START = "2020-01"

# 支付指标单位（数量 vs 金额不同，写入 指标字典 与 月度_CBUAE 表头单位行）
PAYMENT_UNITS = {
    "阿联酋:支票清算笔数(累计)Cheques Cleared Number": "张",
    "阿联酋:支票清算金额(累计)Cheques Cleared Amount": "百万迪拉姆",
    "阿联酋:FTS客户转账笔数(累计)Customer Transfers Number": "笔",
    "阿联酋:FTS客户转账金额(累计)Customer Transfers Amount": "百万迪拉姆",
    "阿联酋:FTS银行转账笔数(累计)Bank Transfers Number": "笔",
    "阿联酋:FTS银行转账金额(累计)Bank Transfers Amount": "百万迪拉姆",
    "阿联酋:FTS国内资金转账总额笔数(累计)Total Fund Transfers Number": "笔",
    "阿联酋:FTS国内资金转账总额金额(累计)Total Fund Transfers Amount": "百万迪拉姆",
}

# 2020 起月频连续；更早公报只含季/年度参考列，不入连续月度序列
PAYMENT_START = "2020-01"

# 表内指标 slug -> CBUAE_INDICATORS 中的名称
PAYMENT_METRIC_INDICATOR = {
    "cheques_number": "阿联酋:支票清算笔数(累计)Cheques Cleared Number",
    "cheques_amount": "阿联酋:支票清算金额(累计)Cheques Cleared Amount",
    "customer_number": "阿联酋:FTS客户转账笔数(累计)Customer Transfers Number",
    "customer_amount": "阿联酋:FTS客户转账金额(累计)Customer Transfers Amount",
    "bank_number": "阿联酋:FTS银行转账笔数(累计)Bank Transfers Number",
    "bank_amount": "阿联酋:FTS银行转账金额(累计)Bank Transfers Amount",
    "total_number": "阿联酋:FTS国内资金转账总额笔数(累计)Total Fund Transfers Number",
    "total_amount": "阿联酋:FTS国内资金转账总额金额(累计)Total Fund Transfers Amount",
}


@dataclass(frozen=True)
class Observation:
    """一个观测期的一个来源 vintage。

    ``values`` 为 15 元组：(政府存款, 政府控股企业存款, 政府信贷, 政府控股企业信贷,
    私人企业信贷, 商业及工业部门信贷, 非居民私人企业存款, 非居民商业及工业部门存款,
    非居民个人存款, 非居民政府及非商业实体存款, 非居民其他金融企业存款, 外币存款总额,
    银行国外资产, 银行国外负债, 个人信贷)。

    政府 4 项始终存在；企业信贷/存款、个人信贷与外币/国外资产负债各项在对应行未单列
    或 PDF 回退月份为 ``None``。
    """

    period: str
    values: tuple[Decimal | None, ...]
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


def _find_source_sheets(
    workbook: object,
) -> tuple[Worksheet, Worksheet, Worksheet, Worksheet]:
    """定位全银行口径的国内信贷、居民/非居民存款、按币种存款、国外资产负债四张工作表。"""

    credit_sheet: Worksheet | None = None
    deposit_sheet: Worksheet | None = None
    currency_sheet: Worksheet | None = None
    foreign_sheet: Worksheet | None = None
    for sheet in workbook.worksheets:
        text = _sheet_text(sheet)
        if "domestic credit" in text and "all banks" in text:
            credit_sheet = sheet
        if (
            "deposits distributed residents / non residents" in text
            and "all banks" in text
        ):
            deposit_sheet = sheet
        if (
            "deposits by type and currency" in text
            and "all banks" in text
        ):
            currency_sheet = sheet
        if (
            "foreign assets and liabilities" in text
            and "all banks" in text
        ):
            foreign_sheet = sheet
    missing = [
        name
        for name, found in (
            ("domestic credit", credit_sheet),
            ("deposits residents/non-residents", deposit_sheet),
            ("deposits by type and currency", currency_sheet),
            ("foreign assets and liabilities", foreign_sheet),
        )
        if found is None
    ]
    if missing:
        raise ValueError(
            "Required all-banks worksheets not found: " + ", ".join(missing)
        )
    return credit_sheet, deposit_sheet, currency_sheet, foreign_sheet


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


def _find_row_optional(
    sheet: Worksheet, accepted_labels: set[str]
) -> int | None:
    """查找首列标签（首个非空单元格）落在 ``accepted_labels`` 的行；找不到返回 ``None``。

    只匹配“行首标签”，避免把表格下方脚注里的同名短语误当成数据行。
    """

    for row_number, row in enumerate(sheet.iter_rows(), start=1):
        label = _row_default_label(row)
        if label in accepted_labels:
            return row_number
    return None


def _row_default_label(row) -> str:
    """返回行内首个非空字符串单元格（作为该行的默认标签）。"""

    for cell in row:
        if isinstance(cell.value, str) and cell.value.strip():
            return _normalize_label(cell.value)
    return ""


def _extract_one_row(
    sheet: Worksheet,
    columns: dict[int, str],
    row_number: int | None,
) -> dict[str, Decimal]:
    """按期间读某一行数值；行不存在时返回空 dict。"""

    if row_number is None:
        return {}
    extracted: dict[str, Decimal] = {}
    for period, column in columns.items():
        value = _to_decimal(sheet.cell(row_number, column).value)
        if value is not None:
            extracted[period] = value
    return extracted


def _extract_corporate_rows(
    sheet: Worksheet,
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """提取 Domestic Credit (All Banks) 表的「私人企业 / 商业及工业部门」两行。

    标签兼容旧格式（Private - Corporate / Business and Industrial Sector **）与新格式
    （Private - Corporate 或 Corporate / Business and Industrial Sector）。

    当公报不再单列 "Business and Industrial Sector" 行（如新格式 2026-05/06），且同时
    单列 "Corporate" 与 "Other Financial Corporations" 两行时，按已验证口径推导：
        商业及工业部门 = 私人企业(Corporate) - 其他金融企业(Other Financial Corporations)
    （该恒等在重叠期逐月成立，见核查；C/BUAE 财务印在同一表。「Commercial & Industrial」注释
     亦印证此拆分。）
    """

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}, {}
    corporate_row = _find_row_optional(
        sheet, {"private - corporate", "corporate"}
    )
    business_row = _find_row_optional(
        sheet, {"business and industrial sector"}
    )
    other_financial_row = _find_row_optional(
        sheet, {"other financial corporations"}
    )

    corporate = _extract_one_row(sheet, columns, corporate_row)
    business = _extract_one_row(sheet, columns, business_row)
    other_financial = _extract_one_row(sheet, columns, other_financial_row)

    # 仅在最新公报未单列 Business 行时，用 Corporate - OtherFinancial 推导缺失期间
    if corporate and other_financial and not business:
        business = {
            period: corporate_value - other_financial[period]
            for period, corporate_value in corporate.items()
            if period in other_financial
        }
    return corporate, business


def _extract_individual_row(
    sheet: Worksheet,
) -> dict[str, Decimal]:
    """提取 Domestic Credit (All Banks) 表的「个人信贷」行。

    兼容老格式行首标签 ``Private - Retail`` 与新格式标签 ``Individual``
    （新格式自 2026-05 起不再单列 Business & Industrial Sector 行，但始终单列
    Individual 行；老格式的 Private - Retail 即个人/居民信贷，与新格式同口径，
    私人企业信贷 + 个人信贷 = Private Sector 总额）。
    """

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}
    row = _find_row_optional(sheet, {"private - retail", "individual"})
    return _extract_one_row(sheet, columns, row)


def _extract_nonresident_deposits(
    sheet: Worksheet,
) -> tuple[dict[str, Decimal], dict[str, Decimal], dict[str, Decimal], dict[str, Decimal]]:
    """提取存款表「非居民」块(2) 的私人企业 / 个人 / 政府及非商业实体 / 其他金融企业存款。

    存款表分两块：(1) 居民 Residents / (2) 非居民 Non-Residents。用户口径取**非居民块
    (2)**，按行首标签（而非块内编号）定位各子项，因新旧公报块内编号顺序不同
    （旧格式 2.2=Non Banking Financial Institutions/2.3=Individuals/2.4=Government；
    新格式 2.2=Individuals/2.3=Government/2.4=Other Financial Corporations），
    故必须按语义标签匹配。

    返回四行：corporate、individuals、government_non_commercial、other_financial；
    ``other_financial`` 兼容 "Other Financial Corporations"（新）与
    "Non Banking Financial Institutions"（旧）。
    """

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}, {}, {}, {}

    block2_start: int | None = None
    corporate_row: int | None = None
    individuals_row: int | None = None
    government_row: int | None = None
    financial_row: int | None = None
    for row_number, row in enumerate(sheet.iter_rows(), start=1):
        block_label = _normalize_label(row[1].value)
        if block_label == "(2)":
            block2_start = row_number
            continue
        if block2_start is None:
            continue
        # 块内标签在第 4 列（index 3），如 'Corporate' / 'Individuals' 等
        label = _normalize_label(row[3].value)
        if corporate_row is None and label == "corporate":
            corporate_row = row_number
        elif individuals_row is None and label == "individuals":
            individuals_row = row_number
        elif government_row is None and "government and non commercial" in label:
            government_row = row_number
        elif financial_row is None and (
            "non banking financial" in label or "other financial" in label
        ):
            financial_row = row_number

    corporate = _extract_one_row(sheet, columns, corporate_row)
    individuals = _extract_one_row(sheet, columns, individuals_row)
    government = _extract_one_row(sheet, columns, government_row)
    other_financial = _extract_one_row(sheet, columns, financial_row)
    return corporate, individuals, government, other_financial


def _extract_total_foreign_currencies(
    sheet: Worksheet,
) -> dict[str, Decimal]:
    """提取按币种存款表（All Banks）的「外币存款总额 / Total Foreign Currencies」行。

    该行在平铺（旧格式，Demand/Local Currency/Foreign Currencies 逐行）与嵌套
    （新格式）两种布局下都以 ``Total Foreign Currencies`` 作为行首标签，跨格式稳定。
    """

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}
    row = _find_row_optional(sheet, {"total foreign currencies"})
    return _extract_one_row(sheet, columns, row)


def _extract_foreign_assets_liabilities(
    sheet: Worksheet,
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """提取国外资产负债表中「Foreign Assets」与「Foreign Liabilities」两个汇总行。"""

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}, {}
    assets_row = _find_row_optional(sheet, {"foreign assets"})
    liabilities_row = _find_row_optional(sheet, {"foreign liabilities"})
    return (
        _extract_one_row(sheet, columns, assets_row),
        _extract_one_row(sheet, columns, liabilities_row),
    )


def _find_row_contains(sheet: Worksheet, tokens: tuple[str, ...]) -> int | None:
    """查找首列标签包含 ``tokens`` 中任一子串的行；找不到返回 ``None``。"""

    for row_number, row in enumerate(sheet.iter_rows(), start=1):
        label = _row_default_label(row)
        if any(token in label for token in tokens):
            return row_number
    return None


def _extract_payment_sheet(
    sheet: Worksheet, kind: str
) -> dict[str, dict[str, Decimal]]:
    """提取 Cheques(FTS 之外的支票清算) 表：period -> {metric: 年内累计值}。

    ``kind='cheques'`` 时提取去 "Number of Cheques" 与 "Amount" 两行（金额百万迪拉姆）。
    """

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}
    if kind == "cheques":
        number_row = _find_row_contains(sheet, ("number of che",))
        amount_row = _find_row_contains(sheet, ("amount",))
        extracted: dict[str, dict[str, Decimal]] = {}
        for metric, row_number in (
            ("cheques_number", number_row),
            ("cheques_amount", amount_row),
        ):
            for period, value in _extract_one_row(sheet, columns, row_number).items():
                extracted.setdefault(period, {})[metric] = value
        return extracted
    raise ValueError(f"Unsupported payment sheet kind: {kind}")


def _extract_fts_rows(sheet: Worksheet) -> dict[str, dict[str, Decimal]]:
    """提取 FTS 表三块（Customer / Bank / Total）的笔数与金额。

    行结构：分区标题（Customer to Customer / Bank to Bank / Total Domestic Fund
    Transfers）后跟 "Number of Transfers" 与 "Amount" 两行。
    """

    try:
        columns = _header_columns(sheet)
    except ValueError:
        return {}
    section: str | None = None
    rows_by_metric: dict[str, int] = {}
    for row_number, row in enumerate(sheet.iter_rows(), start=1):
        label = _row_default_label(row)
        if "customer to customer" in label:
            section = "customer"
        elif "bank to bank" in label:
            section = "bank"
        elif "total domestic" in label:
            section = "total"
        if section is None:
            continue
        if "number of trans" in label:
            rows_by_metric[f"{section}_number"] = row_number
        elif label.startswith("amount"):
            rows_by_metric[f"{section}_amount"] = row_number

    extracted: dict[str, dict[str, Decimal]] = {}
    for metric, row_number in rows_by_metric.items():
        for period, value in _extract_one_row(sheet, columns, row_number).items():
            extracted.setdefault(period, {})[metric] = value
    return extracted


def extract_payment_rows(path: Path) -> list[dict]:
    """从一份公报工作簿提取 Cheques 与 FTS 两表的逐月累计长表行。

    返回 dict 列表：{period: date, indicator, value, source_period, source_file}。
    仅解析 xlsx；PDF 回退不覆盖支付表（pdf 为主的月份该项留空）。
    """

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        cheques_sheet: Worksheet | None = None
        fts_sheet: Worksheet | None = None
        for sheet in workbook.worksheets:
            text = _sheet_text(sheet)
            if cheques_sheet is None and "cheques clear" in text and "number of che" in text:
                cheques_sheet = sheet
            # FTS 表按表名（48/37 FTS）或文本特征识别；勿要求 'bank to bank'
            # 出现在表头前 10 行（2020 等早期公报该分区行还在更下方）。
            if fts_sheet is None and (
                "fts" in _normalize_label(sheet.title)
                or "fund transfer" in text
                or "uaefts" in text
            ):
                fts_sheet = sheet
        source_period = _source_period(path)
        combined: dict[str, dict[str, Decimal]] = {}
        if cheques_sheet is not None:
            for period, metrics in _extract_payment_sheet(cheques_sheet, "cheques").items():
                combined.setdefault(period, {}).update(metrics)
        if fts_sheet is not None:
            for period, metrics in _extract_fts_rows(fts_sheet).items():
                combined.setdefault(period, {}).update(metrics)
    finally:
        workbook.close()

    rows: list[dict] = []
    for period, metrics in combined.items():
        for metric, value in metrics.items():
            indicator = PAYMENT_METRIC_INDICATOR.get(metric)
            if indicator is None:
                continue
            rows.append(
                {
                    "period": _month_end(period),
                    "indicator": indicator,
                    "value": value,
                    "source_period": source_period,
                    "source_file": path.name,
                }
            )
    return rows


def _indicator_unit(name: str) -> str:
    """返回单个指标的计量单位（支付表数量/金额单位不同）。"""

    return PAYMENT_UNITS.get(name, UNIT)


def _payment_rows_selected(
    rows: Iterable[dict], start_period: str
) -> list[dict]:
    """为每个 (period, indicator) 保留最新 vintage 的支付长表行，并过滤到月频区间。"""

    best: dict[tuple, dict] = {}
    for row in rows:
        period = row["period"].strftime("%Y-%m")
        if period < start_period:
            continue
        key = (period, row["indicator"])
        current = best.get(key)
        if current is None or (row["source_period"], row["source_file"]) > (
            current["source_period"],
            current["source_file"],
        ):
            best[key] = row
    return list(best.values())


def extract_workbook(path: Path) -> list[Observation]:
    """从一个工作簿提取所有完整的期间观测。"""

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        (
            credit_sheet,
            deposit_sheet,
            currency_sheet,
            foreign_sheet,
        ) = _find_source_sheets(workbook)
        deposits = _extract_sheet_rows(
            deposit_sheet,
            ({"government"}, {"gres"}),
        )
        credits = _extract_sheet_rows(
            credit_sheet,
            ({"government"}, {"public sector", "public sector (gres)"}),
        )
        corporate, business = _extract_corporate_rows(credit_sheet)
        individual = _extract_individual_row(credit_sheet)
        (
            nonres_corporate,
            nonres_individuals,
            nonres_government,
            nonres_other_financial,
        ) = _extract_nonresident_deposits(deposit_sheet)
        # 商业及工业部门存款 = Corporate − OtherFinancial（与信贷侧同口径恒等推导）
        deposit_business = {
            period: corporate_value - nonres_other_financial[period]
            for period, corporate_value in nonres_corporate.items()
            if period in nonres_other_financial
        }
        total_foreign_currencies = _extract_total_foreign_currencies(currency_sheet)
        foreign_assets, foreign_liabilities = _extract_foreign_assets_liabilities(
            foreign_sheet
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
                    corporate.get(period),
                    business.get(period),
                    nonres_corporate.get(period),
                    deposit_business.get(period),
                    nonres_individuals.get(period),
                    nonres_government.get(period),
                    nonres_other_financial.get(period),
                    total_foreign_currencies.get(period),
                    foreign_assets.get(period),
                    foreign_liabilities.get(period),
                    individual.get(period),
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
        # PDF 回退仅政府存贷 4 项；企业/外币/国外资产负债 10 项以 None 占位
        values=(
            *deposit_values,
            *credit_values,
            None, None, None, None, None, None, None, None, None, None, None,
        ),
        source_period=period,
        source_file=path.name,
    )


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
    """把宽表观测展开为 (period, indicator) 长表入库行（仅信贷/存贷款组）。"""

    rows: list[dict] = []
    for observation in observations:
        for (indicator, _), value in zip(
            CBUAE_CREDIT_INDICATORS, observation.values
        ):
            if value is None:
                # 该指标本月无值（如企业信贷未单列或公报缺失），不入库
                continue
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
            "unit": _indicator_unit(name),
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
    ``skip_download``/``force`` 仅作签名兼容。数据一律直接来自 CBUAE 公报，
    不依赖任何 Wind 序列。
    """

    observations: list[Observation] = []
    payment_rows: list[dict] = []
    errors: list[str] = []
    workbook_paths = sorted(RAW_DIR.glob("20??-??.xlsx"))
    for path in workbook_paths:
        try:
            observations.extend(extract_workbook(path))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
        try:
            payment_rows.extend(extract_payment_rows(path))
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

    payment_selected = _payment_rows_selected(payment_rows, primary_start)
    rows = _long_rows(selected) + payment_selected
    with _transaction(con):
        db.replace(con, "cbuae_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    payment_periods = sorted({row["period"].strftime("%Y-%m") for row in payment_selected})
    note = (
        f"{len(selected)} 个观察月（{selected[0].period} 至 {selected[-1].period}）"
        f"× {len(CBUAE_CREDIT_INDICATORS)} 存贷款指标；"
        f"支付体系 {len(CBUAE_PAYMENT_INDICATORS)} 指标"
        f"（{'/'.join((payment_periods[0], payment_periods[-1])) if payment_periods else '无'}）；"
        f"vintage 修订 {revised_periods} 期"
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
    # 允许部分指标缺值（如企业信贷在公报未单列或公报缺失的月份为 None），
    # 写表时对应单元格留空。

    payload = {
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月",
        "unit": UNIT,
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {
                "name": name,
                "type": indicator_type,
                "industry": INDUSTRY,
                "unit": _indicator_unit(name),
            }
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
    print("    （xlsx 优先、pdf 回退补缺）并入库 cbuae_monthly 长表")
    print("  merge(workbook_path) 把表写回 月度_CBUAE")
    print("  本文件直接运行不执行任何下载或工作簿写入。")