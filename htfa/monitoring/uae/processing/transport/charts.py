from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.processing.periods import within_month_window


def _windowed(frame: pd.DataFrame, last_month: pd.Period) -> pd.DataFrame:
    return within_month_window(
        frame, first_month=last_month - 36, last_month=last_month
    ).dropna(how="all")
