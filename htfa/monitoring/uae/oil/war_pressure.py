"""阿联酋战争压力月度数据的工作簿适配器。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.data.economic_workbook import SheetSeriesMetadata


WAM_SHEET = "月度_WAM"
OBSERVATION_DAYS_LABEL = "观测天数"
OBSERVATION_DAYS_INDICATOR = "阿联酋军事打击:观测天数(Observation Days)"

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
    observation_days: pd.Series


def load_war_pressure_data(
    source: PublishedUAEData,
) -> WarPressureData:
    """读取 WAM 军事打击及观测天数序列。"""

    source = require_published_source(source)
    with source.open() as tables:
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
                tables,
                sheet_name=WAM_SHEET,
                targets=targets,
                allowed_frequencies={"月"},
                expected_unit=expected_unit,
                zero_is_missing=False,
            )
            frames.append(frame)
            metadata.update(group_metadata)

        observation_frame, observation_metadata = parse_target_sheet(
            tables,
            sheet_name=WAM_SHEET,
            targets=((OBSERVATION_DAYS_LABEL, OBSERVATION_DAYS_INDICATOR),),
            allowed_frequencies={"月"},
            expected_unit="天",
            zero_is_missing=False,
        )
        metadata.update(observation_metadata)

    values = pd.concat(frames, axis=1, sort=False).sort_index()
    return WarPressureData(
        values=values,
        metadata=metadata,
        observation_days=observation_frame[OBSERVATION_DAYS_LABEL],
    )


__all__ = [
    "BALLISTIC_LABEL",
    "CRUISE_LABEL",
    "PRESSURE_LABEL",
    "OBSERVATION_DAYS_INDICATOR",
    "OBSERVATION_DAYS_LABEL",
    "RAW_LABELS",
    "UAV_LABEL",
    "WAM_INDICATORS",
    "WAM_SHEET",
    "WarPressureData",
    "load_war_pressure_data",
]
