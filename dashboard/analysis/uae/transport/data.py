"""阿联酋交通物流月度监测（IMF PortWatch：霍尔木兹海峡 + UAE 港口）。

数据来自工作簿「月度_PortWatch」sheet（先入 duckdb 再写 Excel 的月度聚合表）：
- 霍尔木兹通道 3 指标：油轮载货容量（吨）、载货总容量（吨）、油轮过境次数（艘次）；
- UAE 港口 1 指标：港口到港总次数（艘次）。

四大指标是"战争对海运影响"最灵敏的组合（2026-03 美伊战争断崖实证）：
霍尔木兹油轮容量环比 -98%、UAE 港口到港 -77%。图表统一带 2026-03
战争基准线（红色虚线），窗口锚定最新完整月往前 36 个月。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    open_uae_workbook,
    parse_target_sheet,
)

PORTWATCH_SHEET = "月度_PortWatch"

# (显示名, 工作簿指标名, 单位)。指标名与「月度_PortWatch」写表一致；
# 解析时经 normalize_indicator_name 全角/冒号归一匹配。
HORMUZ_TANKER_CAPACITY = "霍尔木兹油轮容量"
HORMUZ_CAPACITY = "霍尔木兹总容量"
HORMUZ_TANKER_CALLS = "霍尔木兹油轮过境"
UAE_PORT_CALLS = "UAE港口总到港"

CALLS_TARGETS: tuple[tuple[str, str], ...] = (
    (HORMUZ_TANKER_CALLS, "霍尔木兹:油轮过境次数:当月值"),
    (UAE_PORT_CALLS, "阿联酋:港口到港总次数:当月值"),
)
TON_TARGETS: tuple[tuple[str, str], ...] = (
    (HORMUZ_CAPACITY, "霍尔木兹:载货容量:当月值"),
    (HORMUZ_TANKER_CAPACITY, "霍尔木兹:油轮载货容量:当月值"),
)

ALL_COLUMNS: tuple[str, ...] = (
    HORMUZ_TANKER_CALLS,
    HORMUZ_CAPACITY,
    HORMUZ_TANKER_CAPACITY,
    UAE_PORT_CALLS,
)


@dataclass(frozen=True)
class TransportData:
    """交通物流月度的最小数据集（4 个 PortWatch 指标）。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_transport_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> TransportData:
    """只读取「月度_PortWatch」的 4 个指标（艘次、吨两类单位）。

    由于 sheet 内单位混合，按单位分两次调用共享的 parse_target_sheet，
    再按月份对齐合并。
    """

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        calls_frame, calls_metadata = parse_target_sheet(
            excel_file,
            sheet_name=PORTWATCH_SHEET,
            targets=CALLS_TARGETS,
            allowed_frequencies={"月", "月度"},
            expected_unit="艘次",
        )
        ton_frame, ton_metadata = parse_target_sheet(
            excel_file,
            sheet_name=PORTWATCH_SHEET,
            targets=TON_TARGETS,
            allowed_frequencies={"月", "月度"},
            expected_unit="吨",
        )
        values = pd.concat([calls_frame, ton_frame], axis=1, sort=False).sort_index()
        metadata = {**calls_metadata, **ton_metadata}

    return TransportData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


def latest_complete_month(values: pd.DataFrame) -> pd.Timestamp:
    """返回 4 个指标均有效的最新月份。"""

    complete = values.dropna(how="any").sort_index()
    if complete.empty:
        raise ValueError("月度_PortWatch 没有四个指标均完整的月份")
    return pd.Timestamp(complete.index[-1])


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

    latest = latest_complete_month(values).to_period("M")
    reference = (
        pd.Timestamp.today()
        if today is None
        else pd.Timestamp(today).normalize()
    ).to_period("M")
    if latest == reference:
        return latest - 1
    return latest


__all__ = [
    "ALL_COLUMNS",
    "CALLS_TARGETS",
    "HORMUZ_CAPACITY",
    "HORMUZ_TANKER_CALLS",
    "HORMUZ_TANKER_CAPACITY",
    "PORTWATCH_SHEET",
    "TON_TARGETS",
    "TransportData",
    "UAE_PORT_CALLS",
    "anchor_last_month",
    "latest_complete_month",
    "load_transport_data",
]