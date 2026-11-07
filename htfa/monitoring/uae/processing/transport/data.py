from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.periods import (
    anchor_last_month as _anchor_last_month,
)
from htfa.monitoring.uae.contracts.transport.data import TransportData
from htfa.monitoring.uae.data.transport.data import read_transport_data


def load_transport_data(source: PublishedUAEData) -> TransportData:
    """读取交通物流板块所需的海运、迪拜航空和美国↔阿联酋航空指标。

    PortWatch 六个指标是基础数据；扩展 sheet 读取失败时保留基础数据，
    并把错误写入 ``load_errors``，由页面对对应图表显示警告。
    """
    load_errors, metadata, monthly_values, values = read_transport_data(source)
    return TransportData(
        values=values,
        metadata=metadata,
        monthly_values=monthly_values,
        load_errors=load_errors,
    )


def anchor_last_month(
    values: pd.DataFrame, *, today: pd.Timestamp | None = None
) -> pd.Period:
    """锚定**已结束**的最新月份（图表窗口右端，与房地产板块同规则）。

    工作簿最新月若恰为当前自然月（该月未过完、数值为部分月汇总，
    如 2026-08 仅 7 天），则选择上一个完整月；否则取数据侧最新完整月。
    ``today`` 仅测试注入。
    """
    return _anchor_last_month(
        values, today=today, empty_message="交通物流月度指标没有共同完整月份"
    )


def combined_air_series(values, columns, name):
    """Sum all required aviation components without filling missing inputs."""
    return values.loc[:, list(columns)].sum(axis=1, min_count=len(columns)).rename(name)
