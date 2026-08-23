"""阿联酋战争压力月度数据的工作簿适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    open_uae_workbook,
    parse_target_sheet,
)


WAM_SHEET = "月度_WAM"

BALLISTIC_LABEL = "弹道导弹"
CRUISE_LABEL = "巡航导弹"
UAV_LABEL = "无人机"
PRESSURE_LABEL = "战争压力指数"

RAW_LABELS = (BALLISTIC_LABEL, CRUISE_LABEL, UAV_LABEL)
WAM_INDICATORS: tuple[tuple[str, str, str], ...] = (
    (
        BALLISTIC_LABEL,
        "阿联酋军事打击:弹道导弹数量(Ballistic Missiles)",
        "枚",
    ),
    (
        CRUISE_LABEL,
        "阿联酋军事打击:巡航导弹数量(Cruise Missiles)",
        "枚",
    ),
    (
        UAV_LABEL,
        "阿联酋军事打击:无人机数量(UAVs)",
        "架",
    ),
    (
        PRESSURE_LABEL,
        "阿联酋战争压力指标(强权重log1p之和,0-100归一化)",
        "指数",
    ),
)


@dataclass(frozen=True)
class WarPressureData:
    """战争压力图表所需的原始三项数据与合成指数。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_war_pressure_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> WarPressureData:
    """读取 ``月度_WAM``，并保留武器数量中的零值观测。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        groups = (
            (WAM_INDICATORS[:2], "枚"),
            (WAM_INDICATORS[2:3], "架"),
            (WAM_INDICATORS[3:], "指数"),
        )
        frames: list[pd.DataFrame] = []
        metadata: dict[str, SheetSeriesMetadata] = {}
        for specifications, expected_unit in groups:
            targets = tuple(
                (display_name, indicator_name)
                for display_name, indicator_name, _ in specifications
            )
            frame, group_metadata = parse_target_sheet(
                excel_file,
                sheet_name=WAM_SHEET,
                targets=targets,
                allowed_frequencies={"月", "月度"},
                expected_unit=expected_unit,
                zero_is_missing=False,
            )
            frames.append(frame)
            metadata.update(group_metadata)

    values = pd.concat(frames, axis=1, sort=False).sort_index()
    return WarPressureData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


__all__ = [
    "BALLISTIC_LABEL",
    "CRUISE_LABEL",
    "PRESSURE_LABEL",
    "RAW_LABELS",
    "UAV_LABEL",
    "WAM_INDICATORS",
    "WAM_SHEET",
    "WarPressureData",
    "load_war_pressure_data",
]
