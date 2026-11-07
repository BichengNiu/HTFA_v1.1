from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class AdditivityResult:
    """总量与分项的可加总性检查。"""

    residual: pd.Series
    within_tolerance: pd.Series


@dataclass(frozen=True)
class ContributionResult:
    """增长率及分项贡献。"""

    total_growth: pd.Series
    contributions: pd.DataFrame
    additivity: AdditivityResult


@dataclass(frozen=True)
class IndustryDiagnosticsResult:
    """行业增长广度、集中度与持续性诊断。"""

    contribution_result: ContributionResult
    breadth: pd.DataFrame
    concentration: pd.DataFrame
    persistence: pd.DataFrame
