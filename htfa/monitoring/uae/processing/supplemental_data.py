from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.periods import through_last_complete_month
from htfa.monitoring.uae.contracts.supplemental_data import ChartSpec
from htfa.monitoring.uae.data.supplemental_data import read_chart_data


def load_chart_data(
    content: PublishedUAEData, spec: ChartSpec, *, today: pd.Timestamp | None = None
) -> tuple[pd.DataFrame, dict, dict[str, str]]:
    """校验原始频率与单位，日度和周度序列按有效观测转换为月均。"""
    metadata, values = read_chart_data(content, spec, today=today)
    reference = (
        pd.Timestamp.today().normalize()
        if today is None
        else pd.Timestamp(today).normalize()
    )
    values = values.loc[values.index <= reference]
    if spec.frequency == "月":
        values = values.loc[values.index.to_period("M") < reference.to_period("M")]
    elif spec.frequency == "日":
        values = pd.DataFrame(
            {
                name: through_last_complete_month(values[name], today=reference)
                .resample("ME")
                .mean()
                for name in values
            }
        )
    elif spec.frequency == "周":
        values = (
            values.loc[values.index.to_period("M") < reference.to_period("M")]
            .resample("ME")
            .mean()
        )
    units = {label: unit for label, _, unit in spec.series}
    if spec.key == "air_transit":
        values["转运占比"] = (
            values["转运量"].div(values["合计货量"].where(values["合计货量"] > 0)) * 100
        )
        units = {"转运量": "吨", "转运占比": "%"}
    values = values.dropna(how="all")
    if values.empty:
        raise ValueError(f"{spec.title}没有可用观测")
    end = values.index.max()
    if spec.window_months is not None:
        values = values.loc[
            values.index >= end - pd.DateOffset(months=spec.window_months)
        ]
    return (values, metadata, units)
