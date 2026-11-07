from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.contracts.government_finance.credit import NONRESIDENT_DEPOSITS
from htfa.monitoring.uae.contracts.government_finance.credit import (
    NONRESIDENT_CORPORATE_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import (
    NONRESIDENT_INDIVIDUALS_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import (
    NONRESIDENT_GOVERNMENT_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import (
    FOREIGN_INFLOW_INDICATORS,
)
from htfa.monitoring.uae.contracts.government_finance.credit import (
    PRIVATE_CREDIT_INDICATORS,
)
from htfa.monitoring.uae.contracts.government_finance.credit import CbuaeSeriesData
from htfa.monitoring.uae.data.government_finance.credit import read_cbuae_series


def load_foreign_inflow_data(source: PublishedUAEData) -> CbuaeSeriesData:
    """读取外资流入三个指标：银行外债、外币存款与外国主体存款（非居民存款合计）。"""
    data = _load_cbuae_series(source, targets=FOREIGN_INFLOW_INDICATORS)
    frame = data.values
    nonresident = frame[
        [
            NONRESIDENT_CORPORATE_DISPLAY,
            NONRESIDENT_INDIVIDUALS_DISPLAY,
            NONRESIDENT_GOVERNMENT_DISPLAY,
        ]
    ].sum(axis=1, min_count=3)
    frame = frame.copy()
    frame[NONRESIDENT_DEPOSITS] = nonresident
    return CbuaeSeriesData(values=frame, metadata=data.metadata)


def load_private_credit_data(source: PublishedUAEData) -> CbuaeSeriesData:
    """读取私人企业、个人和工商业贷款三个指标。"""
    return _load_cbuae_series(source, targets=PRIVATE_CREDIT_INDICATORS)


def _load_cbuae_series(
    source: PublishedUAEData, *, targets: tuple[tuple[str, str], ...]
) -> CbuaeSeriesData:
    frame, metadata = read_cbuae_series(source, targets=targets)
    return CbuaeSeriesData(values=frame, metadata=metadata)
