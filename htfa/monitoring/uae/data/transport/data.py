from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.preview.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.transport.data import PORTWATCH_SHEET
from htfa.monitoring.uae.contracts.transport.data import DUBAI_CUSTOMS_AIR_SHEET
from htfa.monitoring.uae.contracts.transport.data import DOTT100_SHEET
from htfa.monitoring.uae.contracts.transport.data import CALLS_TARGETS
from htfa.monitoring.uae.contracts.transport.data import PORT_VOLUME_TARGETS
from htfa.monitoring.uae.contracts.transport.data import DUBAI_CUSTOMS_AIR_AWB_TARGETS
from htfa.monitoring.uae.contracts.transport.data import DUBAI_CUSTOMS_AIR_TOTAL_TARGETS
from htfa.monitoring.uae.contracts.transport.data import DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY
from htfa.monitoring.uae.contracts.transport.data import (
    DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY,
)
from htfa.monitoring.uae.contracts.transport.data import DOTT100_ERROR_KEY
from htfa.monitoring.uae.contracts.transport.data import DOTT100_PASSENGER_TARGETS
from htfa.monitoring.uae.contracts.transport.data import DOTT100_FREIGHT_TARGETS


def read_transport_data(source: PublishedUAEData):
    """读取交通物流板块所需的海运、迪拜航空和美国↔阿联酋航空指标。

    PortWatch 六个指标是基础数据；扩展 sheet 读取失败时保留基础数据，
    并把错误写入 ``load_errors``，由页面对对应图表显示警告。
    """
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        port_volume_frame, port_volume_metadata = parse_target_sheet(
            tables,
            sheet_name=PORTWATCH_SHEET,
            targets=PORT_VOLUME_TARGETS,
            allowed_frequencies={"月", "月度"},
            expected_unit="吨",
        )
        calls_frame, calls_metadata = parse_target_sheet(
            tables,
            sheet_name=PORTWATCH_SHEET,
            targets=CALLS_TARGETS,
            allowed_frequencies={"月", "月度"},
            expected_unit="艘次",
        )
        values = pd.concat(
            [port_volume_frame, calls_frame], axis=1, sort=False
        ).sort_index()
        metadata = {**port_volume_metadata, **calls_metadata}
        load_errors: dict[str, str] = {}
        monthly_frames = [values]
        for sheet_name, targets, unit, error_key in (
            (
                DUBAI_CUSTOMS_AIR_SHEET,
                DUBAI_CUSTOMS_AIR_AWB_TARGETS,
                "张",
                DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY,
            ),
            (
                DUBAI_CUSTOMS_AIR_SHEET,
                DUBAI_CUSTOMS_AIR_TOTAL_TARGETS,
                "吨",
                DUBAI_CUSTOMS_AIR_TOTAL_ERROR_KEY,
            ),
            (DOTT100_SHEET, DOTT100_PASSENGER_TARGETS, "人次", DOTT100_ERROR_KEY),
            (DOTT100_SHEET, DOTT100_FREIGHT_TARGETS, "磅", DOTT100_ERROR_KEY),
        ):
            try:
                frame, group_metadata = parse_target_sheet(
                    tables,
                    sheet_name=sheet_name,
                    targets=targets,
                    allowed_frequencies={"月", "月度"},
                    expected_unit=unit,
                )
            except (KeyError, TypeError, ValueError) as exc:
                load_errors[error_key] = "；".join(
                    (text for text in (load_errors.get(error_key), str(exc)) if text)
                )
                continue
            monthly_frames.append(frame)
            metadata.update(group_metadata)
        monthly_values = pd.concat(monthly_frames, axis=1, sort=False).sort_index()
    return (load_errors, metadata, monthly_values, values)
