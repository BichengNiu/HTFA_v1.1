from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.data.annual import load_annual_data as read_annual_data
from htfa.monitoring.uae.contracts.annual_comparison_contracts import REPORT_UNITS
from htfa.monitoring.uae.contracts.annual import ANNUAL_CHARTS


def displayed_annual_values(frame, top_five):
    """Choose a fixed set using the latest observed year, without zero filling."""
    if not top_five:
        return frame
    names = frame.iloc[-1].dropna().nlargest(5).index
    if names.empty:
        raise ValueError("最新年度没有可用于排序的数据")
    return frame.loc[:, names]


def capital_formation_values(frame, *, total=False, top_five=False):
    """Pair current-price levels with exact prior-calendar-year growth rates."""
    levels = (
        frame[["资本形成总额（现价）"]]
        if total
        else displayed_annual_values(frame, top_five)
    )
    previous_dates = levels.index - pd.DateOffset(years=1)
    previous = levels.reindex(previous_dates).set_axis(levels.index)
    growth = levels.div(previous.where(previous.ne(0))).sub(1).mul(100)
    growth = growth.rename(columns=lambda name: f"{name}同比")
    return levels.join(growth)


def load_annual_data(source):
    """Load validated annual observations for report calculations."""
    return read_annual_data(source)
