from __future__ import annotations
from htfa.monitoring.uae.contracts.indicator_catalog import INDICATOR_SPECS

UAE_ANALYSIS_INDICATOR_NAMES = frozenset(
    (spec.indicator_name for spec in INDICATOR_SPECS)
)
