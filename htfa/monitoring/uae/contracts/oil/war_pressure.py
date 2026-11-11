from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.preview.data.economic_workbook import SheetSeriesMetadata

WAM_SHEET = "月度_WAM"
OBSERVATION_DAYS_LABEL = "观测天数"
OBSERVATION_DAYS_INDICATOR = "阿联酋军事打击:观测天数(Observation Days)"
BALLISTIC_LABEL = "弹道导弹"
CRUISE_LABEL = "巡航导弹"
UAV_LABEL = "无人机"
PRESSURE_LABEL = "战争压力指数"
RAW_LABELS = (BALLISTIC_LABEL, CRUISE_LABEL, UAV_LABEL)
WAM_INDICATORS: tuple[tuple[str, str, str], ...] = (
    (BALLISTIC_LABEL, "阿联酋军事打击:弹道导弹数量(Ballistic Missiles)", "枚"),
    (CRUISE_LABEL, "阿联酋军事打击:巡航导弹数量(Cruise Missiles)", "枚"),
    (UAV_LABEL, "阿联酋军事打击:无人机数量(UAVs)", "架"),
    (PRESSURE_LABEL, "阿联酋战争压力指标(强权重log1p之和,0-100归一化)", "指数"),
)


@dataclass(frozen=True)
class WarPressureData:
    """战争压力图表所需的原始三项数据与合成指数。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    observation_days: pd.Series
