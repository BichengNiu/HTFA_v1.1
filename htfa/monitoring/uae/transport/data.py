"""阿联酋交通物流监测（海运与航空货运）。

数据来自工作簿中的以下 sheet（先入 duckdb 再写 Excel 的聚合表）：
- 「月度_PortWatch」：
- UAE 港口进口/出口总量及油轮进口/出口量（吨）；
- 霍尔木兹过境总次数及油轮过境次数（艘次）。
- 「月度_迪拜海关航空」：迪拜航空货运进口/出口运单数（张）与总量（吨）。
- 「月度_DOTT100」：美国↔阿联酋航空旅客（人次）与航空货运（磅）。

十二个指标用于观察港口货量结构、霍尔木兹通道活动、迪拜航空货运与
美国↔阿联酋航空运输
（2026-03 美伊战争断崖实证）。
图表统一带 2026-03
战争基准线（红色虚线），窗口锚定最新完整月往前 36 个月。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from htfa.monitoring.uae.sheet_reader import (
    SheetSeriesMetadata,
    open_uae_workbook,
    parse_target_sheet,
)
from htfa.monitoring.uae.periods import (
    anchor_last_month as _anchor_last_month,
    latest_complete_month as _latest_complete_month,
)

PORTWATCH_SHEET = "月度_PortWatch"
DUBAI_CUSTOMS_AIR_SHEET = "月度_迪拜海关航空"
DOTT100_SHEET = "月度_DOTT100"

# (显示名, 工作簿指标名, 单位)。指标名与「月度_PortWatch」写表一致；
# 解析时经 normalize_indicator_name 全角/冒号归一匹配。
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
    source_name: str
    monthly_values: pd.DataFrame
    load_errors: dict[str, str]


def _try_parse_target_sheet(
    excel_file: pd.ExcelFile,
    *,
    sheet_name: str,
    targets: tuple[tuple[str, str], ...],
    expected_unit: str,
) -> tuple[
    pd.DataFrame,
    dict[str, SheetSeriesMetadata],
    str | None,
]:
    """读取扩展指标；缺失或协议错误只影响对应图表。"""

    try:
        frame, metadata = parse_target_sheet(
            excel_file,
            sheet_name=sheet_name,
            targets=targets,
            allowed_frequencies={"月", "月度"},
            expected_unit=expected_unit,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return pd.DataFrame(), {}, str(exc)
    return frame, metadata, None


def load_transport_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> TransportData:
    """读取交通物流板块所需的海运、迪拜航空和美国↔阿联酋航空指标。

    PortWatch 六个指标是基础数据；扩展 sheet 读取失败时保留基础数据，
    并把错误写入 ``load_errors``，由页面对对应图表显示警告。
    """

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        port_volume_frame, port_volume_metadata = parse_target_sheet(
            excel_file,
            sheet_name=PORTWATCH_SHEET,
            targets=PORT_VOLUME_TARGETS,
            allowed_frequencies={"月", "月度"},
            expected_unit="吨",
        )
        calls_frame, calls_metadata = parse_target_sheet(
            excel_file,
            sheet_name=PORTWATCH_SHEET,
            targets=CALLS_TARGETS,
            allowed_frequencies={"月", "月度"},
            expected_unit="艘次",
        )
        values = pd.concat(
            [port_volume_frame, calls_frame],
            axis=1,
            sort=False,
        ).sort_index()
        metadata = {**port_volume_metadata, **calls_metadata}
        load_errors: dict[str, str] = {}

        customs_awb_frame, customs_awb_metadata, error = _try_parse_target_sheet(
            excel_file,
            sheet_name=DUBAI_CUSTOMS_AIR_SHEET,
            targets=DUBAI_CUSTOMS_AIR_AWB_TARGETS,
            expected_unit="张",
        )
        if error:
            load_errors[DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY] = error
        metadata.update(customs_awb_metadata)

        customs_total_frame, customs_total_metadata, error = (
            _try_parse_target_sheet(
                excel_file,
                sheet_name=DUBAI_CUSTOMS_AIR_SHEET,
                targets=DUBAI_CUSTOMS_AIR_TOTAL_TARGETS,
                expected_unit="吨",
            )
        )
        if error:
            load_errors[DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY] = error
        metadata.update(customs_total_metadata)

        customs_frame = pd.concat(
            [customs_awb_frame, customs_total_frame],
            axis=1,
            sort=False,
        ).sort_index()

        dot_passenger_frame, dot_passenger_metadata, error = (
            _try_parse_target_sheet(
                excel_file,
                sheet_name=DOTT100_SHEET,
                targets=DOTT100_PASSENGER_TARGETS,
                expected_unit="人次",
            )
        )
        dot_errors: list[str] = []
        if error:
            dot_errors.append(error)
        metadata.update(dot_passenger_metadata)

        dot_freight_mail_frame, dot_freight_mail_metadata, error = (
            _try_parse_target_sheet(
                excel_file,
                sheet_name=DOTT100_SHEET,
                targets=DOTT100_FREIGHT_TARGETS,
                expected_unit="磅",
            )
        )
        if error:
            dot_errors.append(error)
        metadata.update(dot_freight_mail_metadata)
        if dot_errors:
            load_errors[DOTT100_ERROR_KEY] = "；".join(dot_errors)
        dot_frame = pd.concat(
            [dot_passenger_frame, dot_freight_mail_frame],
            axis=1,
            sort=False,
        ).sort_index()

        monthly_values = pd.concat(
            [values, customs_frame, dot_frame],
            axis=1,
            sort=False,
        ).sort_index()

    return TransportData(
        values=values,
        metadata=metadata,
        source_name=source_name,
        monthly_values=monthly_values,
        load_errors=load_errors,
    )


def latest_complete_month(values: pd.DataFrame) -> pd.Timestamp:
    """返回输入月度指标均有效的最新月份。"""

    return _latest_complete_month(
        values,
        empty_message="交通物流月度指标没有共同完整月份",
    )


def anchor_last_month(
    values: pd.DataFrame,
    *,
    today: pd.Timestamp | None = None,
) -> pd.Period:
    """锚定**已结束**的最新月份（图表窗口右端，与房地产板块同规则）。

    工作簿最新月若恰为当前自然月（该月未过完、数值为部分月汇总，
    如 2026-08 仅 7 天），回退一个月；否则取数据侧最新完整月。
    ``today`` 仅测试注入。
    """

    return _anchor_last_month(
        values,
        today=today,
        empty_message="交通物流月度指标没有共同完整月份",
    )


__all__ = [
    "CALLS_TARGETS",
    "DUBAI_AIR_EXPORT_AWBS",
    "DUBAI_AIR_EXPORT_TOTAL",
    "DUBAI_AIR_IMPORT_AWBS",
    "DUBAI_AIR_IMPORT_TOTAL",
    "DUBAI_CUSTOMS_AIR_SHEET",
    "DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY",
    "DUBAI_CUSTOMS_AIR_AWB_TARGETS",
    "DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY",
    "DUBAI_CUSTOMS_AIR_TOTAL_TARGETS",
    "DOTT100_ERROR_KEY",
    "DOTT100_FREIGHT_TARGETS",
    "DOTT100_PASSENGER_TARGETS",
    "DOTT100_SHEET",
    "HORMUZ_TOTAL_CALLS",
    "HORMUZ_TANKER_CALLS",
    "PORTWATCH_SHEET",
    "PORT_VOLUME_TARGETS",
    "TransportData",
    "UAE_PORT_EXPORT_TOTAL",
    "UAE_PORT_IMPORT_TOTAL",
    "UAE_PORT_TANKER_EXPORT",
    "UAE_PORT_TANKER_IMPORT",
    "US_UAE_AIR_FREIGHT",
    "US_UAE_AIR_PASSENGERS",
    "anchor_last_month",
    "latest_complete_month",
    "load_transport_data",
]
