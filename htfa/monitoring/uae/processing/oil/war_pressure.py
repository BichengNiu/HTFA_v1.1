from __future__ import annotations
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.contracts.oil.war_pressure import OBSERVATION_DAYS_LABEL
from htfa.monitoring.uae.contracts.oil.war_pressure import WAM_INDICATORS
from htfa.monitoring.uae.contracts.oil.war_pressure import WarPressureData
from htfa.monitoring.uae.data.oil.war_pressure import read_war_pressure_data


def load_war_pressure_data(source: PublishedUAEData) -> WarPressureData:
    """读取 WAM 军事打击及观测天数序列。"""
    frame, metadata = read_war_pressure_data(source)
    values = frame[[label for label, _, _ in WAM_INDICATORS]].dropna(how="all")
    return WarPressureData(
        values=values,
        metadata=metadata,
        observation_days=frame[OBSERVATION_DAYS_LABEL].dropna(),
    )
