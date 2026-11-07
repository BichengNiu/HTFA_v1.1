from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.data.economic_workbook import SheetSeriesMetadata

CBUAE_SHEET = "月度_CBUAE"
FOREIGN_LIABILITIES = "阿联酋:银行国外负债(Foreign Liabilities)"
FOREIGN_LIABILITIES_DISPLAY = "银行外债"
FOREIGN_CURRENCIES = "阿联酋:外币存款(Total Foreign Currencies)"
FOREIGN_CURRENCIES_DISPLAY = "外币存款"
NONRESIDENT_DEPOSITS = "外国主体存款"
NONRESIDENT_CORPORATE = "阿联酋:非居民存款:私人企业存款(Private Corporate Deposit)"
NONRESIDENT_CORPORATE_DISPLAY = "非居民私人企业存款"
NONRESIDENT_INDIVIDUALS = "阿联酋:非居民存款:个人存款(Individuals Deposit)"
NONRESIDENT_INDIVIDUALS_DISPLAY = "非居民个人存款"
NONRESIDENT_GOVERNMENT = "阿联酋:非居民存款:政府及非商业实体存款(Government & Non Commercial Entities Deposit)"
NONRESIDENT_GOVERNMENT_DISPLAY = "非居民政府及非商业实体存款"
PRIVATE_CORPORATE = "阿联酋:国内信贷:私人企业信贷(Private Corporate Credit)"
PRIVATE_CORPORATE_DISPLAY = "私人企业信贷"
INDIVIDUAL = "阿联酋:国内信贷:个人信贷(Individual Credit)"
INDIVIDUAL_DISPLAY = "个人信贷"
BUSINESS_INDUSTRIAL = (
    "阿联酋:国内信贷:商业及工业部门信贷(Business & Industrial Sector Credit)"
)
BUSINESS_INDUSTRIAL_DISPLAY = "工商业贷款"
FOREIGN_INFLOW_INDICATORS: tuple[tuple[str, str], ...] = (
    (FOREIGN_LIABILITIES_DISPLAY, FOREIGN_LIABILITIES),
    (FOREIGN_CURRENCIES_DISPLAY, FOREIGN_CURRENCIES),
    (NONRESIDENT_CORPORATE_DISPLAY, NONRESIDENT_CORPORATE),
    (NONRESIDENT_INDIVIDUALS_DISPLAY, NONRESIDENT_INDIVIDUALS),
    (NONRESIDENT_GOVERNMENT_DISPLAY, NONRESIDENT_GOVERNMENT),
)
PRIVATE_CREDIT_INDICATORS: tuple[tuple[str, str], ...] = (
    (PRIVATE_CORPORATE_DISPLAY, PRIVATE_CORPORATE),
    (INDIVIDUAL_DISPLAY, INDIVIDUAL),
    (BUSINESS_INDUSTRIAL_DISPLAY, BUSINESS_INDUSTRIAL),
)
FOREIGN_SERIES = (
    f"{FOREIGN_LIABILITIES_DISPLAY}同比",
    f"{FOREIGN_CURRENCIES_DISPLAY}同比",
    f"{NONRESIDENT_DEPOSITS}同比",
)
PRIVATE_CREDIT_SERIES = (
    f"{PRIVATE_CORPORATE_DISPLAY}同比",
    f"{INDIVIDUAL_DISPLAY}同比",
    f"{BUSINESS_INDUSTRIAL_DISPLAY}同比",
)


@dataclass(frozen=True)
class CbuaeSeriesData:
    """月度_CBUAE 的一组扩展指标（外资流入或企业/居民信贷）。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
