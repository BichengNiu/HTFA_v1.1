from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.data.economic_workbook import SheetSeriesMetadata

PORTWATCH_SHEET = "月度_PortWatch"
DUBAI_CUSTOMS_AIR_SHEET = "月度_迪拜海关航空"
DOTT100_SHEET = "月度_DOTT100"
UAE_PORT_IMPORT_TOTAL = "阿联酋港口进口总量"
UAE_PORT_EXPORT_TOTAL = "阿联酋港口出口总量"
UAE_PORT_TANKER_IMPORT = "阿联酋港口油轮进口量"
UAE_PORT_TANKER_EXPORT = "阿联酋港口油轮出口量"
HORMUZ_TOTAL_CALLS = "霍尔木兹过境总次数"
HORMUZ_TANKER_CALLS = "霍尔木兹油轮过境"
DUBAI_AIR_IMPORT_AWBS = "迪拜航空货运_进口运单数(张)"
DUBAI_AIR_EXPORT_AWBS = "迪拜航空货运_出口运单数(张)"
DUBAI_AIR_IMPORT_TOTAL = "迪拜航空货运_进口总量(吨)"
DUBAI_AIR_EXPORT_TOTAL = "迪拜航空货运_出口总量(吨)"
US_UAE_AIR_PASSENGERS = "美国↔阿联酋_航空旅客_合计(人次)"
US_UAE_AIR_FREIGHT = "美国↔阿联酋_航空货运_合计(磅)"
CALLS_TARGETS: tuple[tuple[str, str], ...] = (
    (HORMUZ_TOTAL_CALLS, "霍尔木兹:过境总次数:当月值"),
    (HORMUZ_TANKER_CALLS, "霍尔木兹:油轮过境次数:当月值"),
)
PORT_VOLUME_TARGETS: tuple[tuple[str, str], ...] = (
    (UAE_PORT_IMPORT_TOTAL, "阿联酋:港口进口总量:当月值"),
    (UAE_PORT_EXPORT_TOTAL, "阿联酋:港口出口总量:当月值"),
    (UAE_PORT_TANKER_IMPORT, "阿联酋:港口油轮进口量:当月值"),
    (UAE_PORT_TANKER_EXPORT, "阿联酋:港口油轮出口量:当月值"),
)
DUBAI_CUSTOMS_AIR_AWB_TARGETS: tuple[tuple[str, str], ...] = (
    (DUBAI_AIR_IMPORT_AWBS, DUBAI_AIR_IMPORT_AWBS),
    (DUBAI_AIR_EXPORT_AWBS, DUBAI_AIR_EXPORT_AWBS),
)
DUBAI_CUSTOMS_AIR_TOTAL_TARGETS: tuple[tuple[str, str], ...] = (
    (DUBAI_AIR_IMPORT_TOTAL, DUBAI_AIR_IMPORT_TOTAL),
    (DUBAI_AIR_EXPORT_TOTAL, DUBAI_AIR_EXPORT_TOTAL),
)
DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY = f"{DUBAI_CUSTOMS_AIR_SHEET}:运单数"
DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY = f"{DUBAI_CUSTOMS_AIR_SHEET}:总量"
DOTT100_ERROR_KEY = f"{DOTT100_SHEET}:航空指标"
DOTT100_PASSENGER_TARGETS: tuple[tuple[str, str], ...] = (
    (US_UAE_AIR_PASSENGERS, US_UAE_AIR_PASSENGERS),
)
DOTT100_FREIGHT_TARGETS: tuple[tuple[str, str], ...] = (
    (US_UAE_AIR_FREIGHT, US_UAE_AIR_FREIGHT),
)


@dataclass(frozen=True)
class TransportData:
    """交通物流面板数据。

    ``values`` 承载六个 PortWatch 指标；``monthly_values`` 承载航空扩展序列。
    """

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    monthly_values: pd.DataFrame
    load_errors: dict[str, str]
