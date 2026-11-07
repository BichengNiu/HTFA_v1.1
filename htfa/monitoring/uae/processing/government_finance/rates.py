from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.sources import translate_source_text
from htfa.monitoring.uae.processing.periods import through_last_complete_month
from htfa.monitoring.uae.contracts.government_finance.rates import RATES_SHEET
from htfa.monitoring.uae.contracts.government_finance.rates import US_OVERNIGHT_DISPLAY
from htfa.monitoring.uae.contracts.government_finance.rates import RATES_INDICATORS
from htfa.monitoring.uae.contracts.government_finance.rates import RatesData
from htfa.monitoring.uae.data.government_finance.rates import read_rates_data


def load_rates_data(
    source: PublishedUAEData, *, today: pd.Timestamp | None = None
) -> RatesData:
    """读取三条官方利率，聚合为月度均值并统一末期。"""
    frame, metadata = read_rates_data(source, today=today)
    for label, _ in RATES_INDICATORS:
        expected_source = (
            "美联储纽约分行" if label == US_OVERNIGHT_DISPLAY else "阿联酋央行"
        )
        if translate_source_text(metadata[label].source) != expected_source:
            raise ValueError(f"{label}须使用{expected_source}数据，请更新数据库报告")
    monthly = pd.DataFrame(
        {
            label: through_last_complete_month(frame[label], today=today)
            .resample("ME")
            .mean()
            for label, _ in RATES_INDICATORS
        }
    )
    monthly = monthly.dropna(how="all").sort_index()
    common = monthly.dropna(how="any")
    if common.empty:
        raise ValueError(f"{RATES_SHEET} 没有共同可用的完整月份利率观测")
    monthly = monthly.loc[: common.index.max()]
    return RatesData(values=monthly, metadata=metadata)
